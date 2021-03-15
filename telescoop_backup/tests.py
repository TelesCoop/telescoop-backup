import json

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

User = get_user_model()


class UserDetailsTestCase(TestCase):
    def setUp(self):
        User.objects.create_user(
            email="user@mail.com",
            first_name="first",
            last_name="last",
            password="password",
            is_active=True,
        )

    def test_user_details(self):
        user = User.objects.get(email="user@mail.com")
        client = Client()
        client.login(email=user.email, password="password")
        res = client.get(reverse("auth_profile"))
        response_data = json.loads(res.content)
        self.assertEqual(response_data["email"], "user@mail.com")
        self.assertEqual(response_data["first_name"], "first")
