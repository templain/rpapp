import hashlib
import json
import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)
_REDACTED = "[REDACTED]"
_MAX_LOGGED_RESPONSE_LENGTH = 4000
_SENSITIVE_RESPONSE_FIELDS = {
    "password",
    "client_secret",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
}


class ScimError(Exception):
    pass


def _sanitize_response_body(body: str) -> str:
    try:
        parsed_body = json.loads(body)
    except json.JSONDecodeError:
        sanitized = re.sub(
            r"(?i)(password|client_secret|access_token|refresh_token|id_token)"
            r"([\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+",
            rf"\1\2{_REDACTED}",
            body,
        )
    else:

        def redact_sensitive_values(value):
            if isinstance(value, dict):
                return {
                    key: (
                        _REDACTED
                        if key.casefold() in _SENSITIVE_RESPONSE_FIELDS
                        else redact_sensitive_values(item)
                    )
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [redact_sensitive_values(item) for item in value]
            return value

        sanitized = json.dumps(
            redact_sensitive_values(parsed_body),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    if len(sanitized) > _MAX_LOGGED_RESPONSE_LENGTH:
        return sanitized[:_MAX_LOGGED_RESPONSE_LENGTH] + "...[truncated]"
    return sanitized


def _get_scim_access_token() -> str:
    if not settings.SCIM_CLIENT_ID or not settings.SCIM_CLIENT_SECRET:
        raise ScimError(
            "SCIM OAuth client credentials are not configured. "
            "Set GLUU_SCIM_CLIENT_ID and GLUU_SCIM_CLIENT_SECRET."
        )
    if settings.SCIM_TOKEN_AUTH_METHOD not in {
        "client_secret_basic",
        "client_secret_post",
    }:
        raise ScimError("Unsupported SCIM token endpoint authentication method.")

    cache_material = "\0".join(
        (
            settings.OIDC_OP_TOKEN_ENDPOINT,
            settings.SCIM_CLIENT_ID,
            settings.SCIM_CLIENT_SECRET,
            settings.SCIM_SCOPE,
            settings.SCIM_TOKEN_AUTH_METHOD,
        )
    )
    cache_key = "scim_access_token:" + hashlib.sha256(
        cache_material.encode()
    ).hexdigest()
    cached_token = cache.get(cache_key)
    if cached_token:
        return cached_token

    data = {"grant_type": "client_credentials"}
    auth = None
    if settings.SCIM_SCOPE:
        data["scope"] = settings.SCIM_SCOPE
    if settings.SCIM_TOKEN_AUTH_METHOD == "client_secret_basic":
        auth = HTTPBasicAuth(settings.SCIM_CLIENT_ID, settings.SCIM_CLIENT_SECRET)
    else:
        data["client_id"] = settings.SCIM_CLIENT_ID
        data["client_secret"] = settings.SCIM_CLIENT_SECRET

    try:
        response = requests.post(
            settings.OIDC_OP_TOKEN_ENDPOINT,
            data=data,
            auth=auth,
            timeout=settings.SCIM_TIMEOUT_SECONDS,
            verify=settings.SCIM_VERIFY_SSL,
        )
    except requests.RequestException as exc:
        raise ScimError("Gluu OAuth token endpoint could not be reached.") from exc

    if not response.ok:
        raise ScimError(
            f"Gluu OAuth token request failed (HTTP {response.status_code}). "
            "Check the SCIM client credentials, grant type, authentication method, and scopes."
        )
    try:
        token_response = response.json()
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError) as exc:
        raise ScimError("Gluu OAuth token endpoint returned invalid JSON.") from exc

    access_token = token_response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ScimError("Gluu OAuth token response did not contain an access token.")

    expires_in = token_response.get("expires_in", 300)
    if not isinstance(expires_in, (int, float)) or expires_in <= 0:
        raise ScimError("Gluu OAuth token response contained an invalid expiry.")
    cache.set(cache_key, access_token, timeout=max(int(expires_in) - 30, 1))
    return access_token


def _request(method: str, path: str, **kwargs) -> dict:
    if not settings.SCIM_BASE_URL or not settings.OIDC_OP_TOKEN_ENDPOINT:
        raise ScimError("SCIM接続設定がありません。管理者に連絡してください。")

    access_token = _get_scim_access_token()
    try:
        response = requests.request(
            method,
            f"{settings.SCIM_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/scim+json",
                "Content-Type": "application/scim+json",
            },
            timeout=settings.SCIM_TIMEOUT_SECONDS,
            verify=settings.SCIM_VERIFY_SSL,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ScimError("SCIMサーバーに接続できませんでした。") from exc

    if not response.ok:
        logger.error(
            "SCIM API returned HTTP %s. Response body (redacted): %s",
            response.status_code,
            _sanitize_response_body(response.text),
        )
        raise ScimError(
            f"SCIMサーバーがユーザー操作を拒否しました (HTTP {response.status_code})。"
        )
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ScimError("SCIMサーバーから不正な応答が返されました。") from exc


def list_users() -> list[dict]:
    users = []
    start_index = 1
    while True:
        result = _request(
            "GET",
            "/Users",
            params={"count": 100, "startIndex": start_index},
        )
        resources = result.get("Resources", [])
        if not isinstance(resources, list):
            raise ScimError("SCIMサーバーのユーザー一覧形式が不正です。")
        users.extend(resources)

        total_results = result.get("totalResults")
        if not isinstance(total_results, int) or total_results < 0:
            raise ScimError("SCIMサーバーのページ情報が不正です。")
        if not resources or len(users) >= total_results:
            return users

        page_start_index = result.get("startIndex", start_index)
        if not isinstance(page_start_index, int) or page_start_index < 1:
            raise ScimError("SCIMサーバーのページ情報が不正です。")
        next_start_index = page_start_index + len(resources)
        if next_start_index <= start_index:
            raise ScimError("SCIMサーバーのページ情報が不正です。")
        start_index = next_start_index


def create_user(
    *,
    user_name: str,
    email: str,
    given_name: str,
    family_name: str,
    password: str,
) -> dict:
    gluu_user_extension = "urn:ietf:params:scim:schemas:extension:gluu:2.0:User"
    payload = {
        "schemas": [
            "urn:ietf:params:scim:schemas:core:2.0:User",
            gluu_user_extension,
        ],
        "userName": user_name,
        "name": {"givenName": given_name, "familyName": family_name},
        "emails": [{"value": email, "primary": True}],
        "active": True,
        "password": password,
        gluu_user_extension: {"role": ["user"]},
    }
    return _request("POST", "/Users", json=payload)
