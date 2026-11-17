from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


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

    query = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(
            settings.LOGOUT_REDIRECT_URL
        ),
        "id_token_hint": id_token,
    }

    return f"{endpoint}?{urlencode(query)}"
