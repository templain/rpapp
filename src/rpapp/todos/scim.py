import requests
from django.conf import settings


class ScimError(Exception):
    pass


def _request(method: str, path: str, **kwargs) -> dict:
    if not settings.SCIM_BASE_URL or not settings.SCIM_BEARER_TOKEN:
        raise ScimError("SCIM接続設定がありません。管理者に連絡してください。")

    try:
        response = requests.request(
            method,
            f"{settings.SCIM_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {settings.SCIM_BEARER_TOKEN}",
                "Accept": "application/scim+json",
                "Content-Type": "application/scim+json",
            },
            timeout=settings.SCIM_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ScimError("SCIMサーバーに接続できませんでした。") from exc

    if not response.ok:
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
    *, user_name: str, email: str, given_name: str, family_name: str
) -> dict:
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": user_name,
        "name": {"givenName": given_name, "familyName": family_name},
        "emails": [{"value": email, "primary": True}],
        "active": True,
    }
    return _request("POST", "/Users", json=payload)
