import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from rpapp.todos.models import Todo
from rpapp.todos.oidc import build_logout_url
from rpapp.todos.authentication import (
    GluuOIDCAuthenticationBackend,
    OIDCUserPermissionError,
)
from rpapp.todos.scim import ScimError, _request, create_user, delete_user, list_users


class TodoAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="owner", password="test-pass")
        self.other_user = user_model.objects.create_user(
            username="other", password="test-pass"
        )
        self.todo = Todo.objects.create(owner=self.owner, title="Private task")

    def test_anonymous_user_is_sent_to_oidc_login(self):
        response = self.client.get(reverse("todo-list"))

        self.assertRedirects(
            response,
            "/oidc/authenticate/?next=/",
            fetch_redirect_response=False,
        )

    def test_user_cannot_edit_or_delete_another_users_todo(self):
        self.client.force_login(self.other_user)

        edit_response = self.client.get(
            reverse("todo-update", kwargs={"pk": self.todo.pk})
        )
        delete_response = self.client.post(
            reverse("todo-delete", kwargs={"pk": self.todo.pk})
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(Todo.objects.filter(pk=self.todo.pk).exists())

    def test_user_sees_only_owned_todos(self):
        Todo.objects.create(owner=self.other_user, title="Other user's task")
        self.client.force_login(self.owner)

        response = self.client.get(reverse("todo-list"))

        self.assertContains(response, "Private task")
        self.assertNotContains(response, "Other user's task")

    def test_logout_control_posts_with_csrf_token(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("todo-list"))

        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'action="/oidc/logout/"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    @override_settings(
        OIDC_OP_LOGOUT_ENDPOINT="https://falcon/oxauth/restv1/end_session",
        OIDC_OP_LOGOUT_URL_METHOD="rpapp.todos.oidc.build_logout_url",
        OIDC_STORE_ID_TOKEN=True,
        OIDC_RP_CLIENT_ID="test-client-id",
    )
    def test_logout_redirects_to_gluu_with_id_token_hint(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["oidc_id_token"] = "test-id-token"
        session.save()

        response = self.client.post(reverse("oidc_logout"), secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlsplit(response["Location"]).path,
            "/oxauth/restv1/end_session",
        )
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["client_id"], ["test-client-id"])
        self.assertEqual(
            query["post_logout_redirect_uri"],
            ["https://testserver/"],
        )
        self.assertEqual(query["id_token_hint"], ["test-id-token"])

    @override_settings(
        OIDC_OP_LOGOUT_ENDPOINT="https://falcon/oxauth/restv1/end_session",
        OIDC_RP_CLIENT_ID="test-client-id",
    )
    def test_gluu_logout_requires_stored_id_token(self):
        request = RequestFactory().post("/")
        request.session = {}

        with self.assertRaises(ImproperlyConfigured):
            build_logout_url(request)

    def test_non_staff_user_cannot_open_user_management(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("user-list"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/oidc/authenticate/"))


class ScimUserManagementViewTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin", password="test-pass", is_staff=True
        )

    @patch("rpapp.todos.views.list_users", return_value=[
        {"id": "user-123", "userName": "sample-user", "active": True}
    ])
    def test_user_row_has_csrf_protected_delete_button(self, list_users_mock):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("user-list"))

        self.assertContains(response, 'action="/manage/users/user-123/delete/"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    @patch("rpapp.todos.views.delete_user")
    def test_delete_user_calls_scim_and_redirects(self, delete_user_mock):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("user-delete", kwargs={"user_id": "user-123"})
        )

        self.assertRedirects(response, reverse("user-list"), fetch_redirect_response=False)
        delete_user_mock.assert_called_once_with("user-123")

    @patch("rpapp.todos.views.delete_user")
    def test_delete_user_rejects_get(self, delete_user_mock):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("user-delete", kwargs={"user_id": "user-123"})
        )

        self.assertEqual(response.status_code, 405)
        delete_user_mock.assert_not_called()

    @patch("rpapp.todos.views.delete_user")
    def test_non_admin_cannot_delete_scim_user(self, delete_user_mock):
        user = get_user_model().objects.create_user(username="regular")
        self.client.force_login(user)

        response = self.client.post(
            reverse("user-delete", kwargs={"user_id": "user-123"})
        )

        self.assertEqual(response.status_code, 302)
        delete_user_mock.assert_not_called()


class ScimApiTests(TestCase):
    @override_settings(
        SCIM_BASE_URL="https://scim.example.test/scim/v2",
        OIDC_OP_TOKEN_ENDPOINT="https://gluu.example.test/oxauth/restv1/token",
        SCIM_CLIENT_ID="scim-client",
        SCIM_CLIENT_SECRET="scim-secret",
        SCIM_SCOPE="",
        SCIM_TOKEN_AUTH_METHOD="client_secret_basic",
        SCIM_VERIFY_SSL=True,
    )
    @patch("rpapp.todos.scim._get_scim_access_token", return_value="test-access-token")
    @patch("rpapp.todos.scim.requests.request")
    def test_delete_user_uses_scim_delete_and_accepts_no_content(
        self, request, get_access_token
    ):
        response = request.return_value
        response.ok = True
        response.status_code = 204
        response.text = ""

        self.assertIsNone(delete_user("user-123"))
        request.assert_called_once()
        self.assertEqual(request.call_args.args[:2], (
            "DELETE",
            "https://scim.example.test/scim/v2/Users/user-123",
        ))

    def test_user_id_is_escaped_in_scim_path(self):
        with patch("rpapp.todos.scim._request") as request:
            delete_user("id/with/slash")

        request.assert_called_once_with("DELETE", "/Users/id%2Fwith%2Fslash")

    @override_settings(
        SCIM_BASE_URL="https://scim.example.test/scim/v2",
        OIDC_OP_TOKEN_ENDPOINT="https://gluu.example.test/oxauth/restv1/token",
        SCIM_CLIENT_ID="scim-client",
        SCIM_CLIENT_SECRET="scim-secret",
        SCIM_SCOPE="",
        SCIM_TOKEN_AUTH_METHOD="client_secret_basic",
        SCIM_VERIFY_SSL=False,
    )
    @patch("rpapp.todos.scim.cache")
    @patch("rpapp.todos.scim.requests.request")
    @patch("rpapp.todos.scim._get_scim_access_token", return_value="test-access-token")
    def test_scim_error_response_body_is_logged_with_secrets_redacted(
        self, get_access_token, request, token_cache
    ):
        response = request.return_value
        response.ok = False
        response.status_code = 400
        response.text = json.dumps(
            {
                "detail": "Invalid SCIM attribute",
                "password": "do-not-log-this",
            }
        )

        with self.assertLogs("rpapp.todos.scim", level="ERROR") as logs:
            with self.assertRaisesRegex(ScimError, "HTTP 400"):
                _request("POST", "/Users", json={"userName": "new-user"})

        self.assertIn("Invalid SCIM attribute", logs.output[0])
        self.assertIn("[REDACTED]", logs.output[0])
        self.assertNotIn("do-not-log-this", logs.output[0])

    @patch("rpapp.todos.scim._request")
    def test_create_user_sends_password_as_scim_attribute(self, request):
        request.return_value = {"userName": "new-user"}

        result = create_user(
            user_name="new-user",
            email="new@example.test",
            given_name="New",
            family_name="User",
            password="example-initial-password",
        )

        self.assertEqual(result["userName"], "new-user")
        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["password"], "example-initial-password")
        gluu_extension = "urn:ietf:params:scim:schemas:extension:gluu:2.0:User"
        self.assertIn(gluu_extension, payload["schemas"])
        self.assertEqual(payload[gluu_extension]["role"], ["user"])
        self.assertNotIn("user_permission", payload)

    @override_settings(
        SCIM_BASE_URL="https://scim.example.test/scim/v2",
        OIDC_OP_TOKEN_ENDPOINT="https://gluu.example.test/oxauth/restv1/token",
        SCIM_CLIENT_ID="scim-client",
        SCIM_CLIENT_SECRET="scim-secret",
        SCIM_SCOPE="https://gluu.org/scim/users.read https://gluu.org/scim/users.write",
        SCIM_TOKEN_AUTH_METHOD="client_secret_basic",
        SCIM_VERIFY_SSL=False,
    )
    @patch("rpapp.todos.scim.cache")
    @patch("rpapp.todos.scim.requests.request")
    @patch("rpapp.todos.scim.requests.post")
    def test_oauth_client_credentials_token_is_used_for_scim(
        self, token_request, scim_request, token_cache
    ):
        token_cache.get.return_value = None
        token_response = token_request.return_value
        token_response.ok = True
        token_response.json.return_value = {
            "access_token": "oauth-access-token",
            "expires_in": 300,
        }
        scim_response = scim_request.return_value
        scim_response.ok = True
        scim_response.json.return_value = {}

        result = _request("GET", "/Users")

        self.assertEqual(result, {})
        self.assertEqual(
            token_request.call_args.args,
            ("https://gluu.example.test/oxauth/restv1/token",),
        )
        self.assertEqual(
            token_request.call_args.kwargs["data"]["grant_type"],
            "client_credentials",
        )
        self.assertEqual(
            token_request.call_args.kwargs["auth"].username,
            "scim-client",
        )
        self.assertFalse(token_request.call_args.kwargs["verify"])
        self.assertEqual(
            scim_request.call_args.kwargs["headers"]["Authorization"],
            "Bearer oauth-access-token",
        )
        self.assertFalse(scim_request.call_args.kwargs["verify"])
        token_cache.set.assert_called_once()

    @override_settings(
        SCIM_BASE_URL="https://scim.example.test/scim/v2",
        OIDC_OP_TOKEN_ENDPOINT="https://gluu.example.test/oxauth/restv1/token",
        SCIM_CLIENT_ID="scim-client",
        SCIM_CLIENT_SECRET="scim-secret",
        SCIM_SCOPE="",
        SCIM_TOKEN_AUTH_METHOD="client_secret_post",
        SCIM_VERIFY_SSL=True,
    )
    @patch("rpapp.todos.scim.cache")
    @patch("rpapp.todos.scim.requests.request")
    @patch("rpapp.todos.scim.requests.post")
    def test_client_secret_post_is_supported(
        self, token_request, scim_request, token_cache
    ):
        token_cache.get.return_value = None
        token_request.return_value.ok = True
        token_request.return_value.json.return_value = {
            "access_token": "oauth-access-token",
            "expires_in": 300,
        }
        scim_request.return_value.ok = True
        scim_request.return_value.json.return_value = {}

        _request("GET", "/Users")

        self.assertIsNone(token_request.call_args.kwargs["auth"])
        self.assertEqual(
            token_request.call_args.kwargs["data"],
            {
                "grant_type": "client_credentials",
                "client_id": "scim-client",
                "client_secret": "scim-secret",
            },
        )

    @patch("rpapp.todos.scim._request")
    def test_user_listing_follows_scim_pages(self, request):
        request.side_effect = [
            {
                "Resources": [{"userName": "first"}],
                "totalResults": 2,
                "startIndex": 1,
            },
            {
                "Resources": [{"userName": "second"}],
                "totalResults": 2,
                "startIndex": 2,
            },
        ]

        users = list_users()

        self.assertEqual([user["userName"] for user in users], ["first", "second"])
        self.assertEqual(request.call_count, 2)


class GluuOIDCAdminPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="oidc-user", email="oidc@example.test"
        )
        self.backend = GluuOIDCAuthenticationBackend()
        self.userinfo: dict[str, object] = {"email": self.user.email}
        self._patch_backend_method("get_userinfo", return_value=self.userinfo)
        self._patch_backend_method("verify_claims", return_value=True)
        self._patch_backend_method(
            "filter_users_by_claims", return_value=[self.user]
        )
        self._patch_backend_method("update_user", return_value=self.user)
        self._patch_backend_method("create_user", return_value=self.user)

    def _patch_backend_method(self, method_name, **kwargs):
        patcher = patch.object(self.backend, method_name, **kwargs)
        mocked_method = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked_method

    @override_settings(
        OIDC_OP_AUTHORIZATION_ENDPOINT="https://gluu.example.test/authorize",
        OIDC_RP_CLIENT_ID="test-client-id",
    )
    def test_login_request_includes_view_profile_scope(self):
        response = self.client.get(
            reverse("oidc_authentication_init"),
            secure=True,
        )

        scopes = parse_qs(urlsplit(response["Location"]).query)["scope"][0].split()
        self.assertIn("view_profile", scopes)

    def test_login_request_includes_s256_pkce_challenge(self):
        response = self.client.get(
            reverse("oidc_authentication_init"),
            secure=True,
        )

        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertRegex(query["code_challenge"][0], r"^[A-Za-z0-9_-]+$")

        state = query["state"][0]
        verifier = self.client.session["oidc_states"][state]["code_verifier"]
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

    def test_admin_claim_in_id_token_grants_staff(self):
        with self.assertLogs("rpapp.todos.authentication", level="INFO") as logs:
            result = self.backend.get_or_create_user(
                "access-token", "id-token", {"user_permission": "admin"}
            )

        self.user.refresh_from_db()
        self.assertEqual(result, self.user)
        self.assertTrue(self.user.is_staff)
        self.assertIn("role=admin", logs.output[0])

    def test_general_user_login_is_logged(self):
        with self.assertLogs("rpapp.todos.authentication", level="INFO") as logs:
            self.backend.get_or_create_user(
                "access-token", "id-token", {"user_permission": "todo_user"}
            )

        self.assertIn("role=general", logs.output[0])

    def test_admin_claim_in_userinfo_grants_staff(self):
        self.userinfo["user_permission"] = ["todo_user", "admin"]
        self.backend.get_or_create_user(
            "access-token", "id-token", {}
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)

    def test_given_and_family_name_claims_are_saved(self):
        self.userinfo.update({"given_name": "Taro", "family_name": "Yamada"})

        self.backend.get_or_create_user(
            "access-token",
            "id-token",
            {"user_permission": "user"},
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Taro")
        self.assertEqual(self.user.last_name, "Yamada")

    def test_full_name_claim_is_saved_when_parts_are_unavailable(self):
        self.userinfo["name"] = "山田 太郎"

        self.backend.get_or_create_user(
            "access-token",
            "id-token",
            {"user_permission": "user"},
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "山田 太郎")

    def test_todo_page_displays_full_name_instead_of_username(self):
        self.user.first_name = "Taro"
        self.user.last_name = "Yamada"
        self.user.save(update_fields=["first_name", "last_name"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("todo-list"))

        self.assertContains(response, "Taro Yamada さんのTodo")
        self.assertNotContains(response, "oidc-user さんのTodo")

    def test_missing_admin_claim_revokes_staff_on_next_login(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        self.backend.get_or_create_user(
            "access-token", "id-token", {"user_permission": "todo_user"}
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_non_admin_substring_does_not_grant_staff(self):
        self.backend.get_or_create_user(
            "access-token", "id-token", {"user_permission": "not-admin"}
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_missing_permission_claim_raises_error(self):
        with self.assertRaisesRegex(
            OIDCUserPermissionError, "claim 'user_permission' is missing"
        ):
            self.backend.get_or_create_user("access-token", "id-token", {})

    def test_invalid_permission_claim_raises_error(self):
        with self.assertRaises(OIDCUserPermissionError):
            self.backend.get_or_create_user(
                "access-token", "id-token", {"user_permission": {"role": "admin"}}
            )
