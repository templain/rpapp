from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _gluu_session_is_alive(request) -> bool:
    access_token = request.session.get("oidc_access_token")
    if not isinstance(access_token, str) or not access_token:
        return False

    userinfo_endpoint = settings.OIDC_OP_USER_ENDPOINT
    if not userinfo_endpoint:
        return False

    try:
        response = requests.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            verify=settings.OIDC_VERIFY_SSL,
            timeout=settings.OIDC_TIMEOUT if hasattr(settings, "OIDC_TIMEOUT") else 10,
        )
    except requests.RequestException:
        return False

    return response.status_code == 200


def build_logout_url(request) -> str:
    endpoint = settings.OIDC_OP_LOGOUT_ENDPOINT
    if not endpoint:
        raise ImproperlyConfigured("GLUU_OIDC_END_SESSION_ENDPOINT is not configured.")

    parsed_endpoint = urlsplit(endpoint)
    if parsed_endpoint.scheme != "https" or not parsed_endpoint.netloc:
        raise ImproperlyConfigured(
            "GLUU_OIDC_END_SESSION_ENDPOINT must be an absolute HTTPS URL."
        )

    id_token = request.session.get("oidc_id_token")
    if not id_token:
        raise ImproperlyConfigured(
            "No OIDC ID token is stored in this session. Log in again before logging out."
        )

    if not _gluu_session_is_alive(request):
        return request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)

    query = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(
            settings.LOGOUT_REDIRECT_URL
        ),
        "id_token_hint": id_token,
    }

    return f"{endpoint}?{urlencode(query)}"
