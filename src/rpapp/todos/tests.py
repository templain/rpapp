from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rpapp.todos.models import Todo
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
