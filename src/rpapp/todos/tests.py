from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from rpapp.todos.models import Todo
from rpapp.todos.oidc import build_logout_url
from rpapp.todos.scim import list_users


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


class ScimApiTests(TestCase):
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
