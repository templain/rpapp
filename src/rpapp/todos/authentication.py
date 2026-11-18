import logging

from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)


class OIDCUserPermissionError(RuntimeError):
    pass


class GluuOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def get_or_create_user(self, access_token, id_token, payload):
        user_info = self.get_userinfo(access_token, id_token, payload)
        if not self.verify_claims(user_info):
            raise SuspiciousOperation("Claims verification failed")

        users = self.filter_users_by_claims(user_info)
        if len(users) == 1:
            user = self.update_user(users[0], user_info)
        elif len(users) > 1:
            raise SuspiciousOperation("Multiple users returned")
        elif self.get_settings("OIDC_CREATE_USER", True):
            user = self.create_user(user_info)
        else:
            logger.debug(
                "Login failed: No user with %s found, and OIDC_CREATE_USER is False",
                self.describe_user_by_claims(user_info),
            )
            return None

        if user is None:
            return None

        permission = self._get_permission_claim(payload, user_info)
        if permission is None:
            raise OIDCUserPermissionError(
                "Required OIDC claim 'user_permission' is missing."
            )

        if isinstance(permission, str):
            normalized_permission = permission.strip().casefold()
            if not normalized_permission:
                raise OIDCUserPermissionError(
                    "OIDC claim 'user_permission' must not be empty."
                )
            is_admin = normalized_permission == "admin"
        elif isinstance(permission, list):
            if not all(isinstance(item, str) for item in permission):
                raise OIDCUserPermissionError(
                    "OIDC claim 'user_permission' must be a string or a list of strings."
                )
            is_admin = any(
                item.strip().casefold() == "admin" for item in permission
            )
        else:
            raise OIDCUserPermissionError(
                "OIDC claim 'user_permission' must be a string or a list of strings."
            )

        if user.is_staff != is_admin:
            user.is_staff = is_admin
            user.save(update_fields=["is_staff"])

        logger.info(
            "OIDC login successful: role=%s",
            "admin" if is_admin else "general",
        )
        return user

    @staticmethod
    def _get_permission_claim(payload, user_info):
        for claims in (payload, user_info):
            if "user_permission" in claims:
                return claims["user_permission"]
        return None
