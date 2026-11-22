import logging

from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)


class OIDCUserPermissionError(RuntimeError):
    pass


class GluuOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def verify_token(self, token, **kwargs):
        payload = super().verify_token(token, **kwargs)
        self._validate_audience(payload)
        return payload

    def get_or_create_user(self, access_token, id_token, payload):
        self._validate_audience(payload)
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

        self._sync_user_name(user, user_info)

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

    def _validate_audience(self, payload):
        client_id = self.get_settings("OIDC_RP_CLIENT_ID", "")
        audience = payload.get("aud") if isinstance(payload, dict) else None

        if not isinstance(client_id, str) or not client_id:
            raise SuspiciousOperation(
                "OIDC client ID is not configured."
            )

        if isinstance(audience, str):
            audience_matches = audience == client_id
        elif isinstance(audience, list):
            audience_matches = (
                all(isinstance(item, str) for item in audience)
                and client_id in audience
            )
        else:
            audience_matches = False

        if not audience_matches:
            raise SuspiciousOperation(
                "ID token audience does not match the configured OIDC client ID."
            )

    @staticmethod
    def _get_permission_claim(payload, user_info):
        for claims in (payload, user_info):
            if "user_permission" in claims:
                return claims["user_permission"]
        return None

    @staticmethod
    def _sync_user_name(user, claims):
        given_name = claims.get("given_name")
        family_name = claims.get("family_name")
        full_name = claims.get("name")

        updates = {}
        if isinstance(given_name, str) and given_name.strip():
            updates["first_name"] = given_name.strip()[:150]
        elif (
            not isinstance(family_name, str) or not family_name.strip()
        ) and isinstance(full_name, str) and full_name.strip():
            updates["first_name"] = full_name.strip()[:150]
            updates["last_name"] = ""

        if isinstance(family_name, str) and family_name.strip():
            updates["last_name"] = family_name.strip()[:150]

        changed_fields = [
            field
            for field, value in updates.items()
            if getattr(user, field) != value
        ]
        if changed_fields:
            for field in changed_fields:
                setattr(user, field, updates[field])
            user.save(update_fields=changed_fields)
