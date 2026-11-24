
import re
import unittest
import uuid
from datetime import date

import support as _support  # noqa: F401  (sets test database before importing app)
from support import csrf_token, login, logout
from app import app
from database import get_user_by_email
from nutrition_storage import entries_on


def register(client, email, password="safe-password-123"):
    page = client.get("/register")
    token_match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    if not token_match:
        raise AssertionError("Registration page did not provide a CSRF token")
    return client.post("/register", data={
        "csrf_token": token_match.group(1).decode(),
        "full_name": "NutriCare Test",
        "email": email,
        "password": password,
        "confirm_password": password,
    })


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.email = "auth-{}@example.com".format(uuid.uuid4().hex)

    def test_registration_creates_hashed_user_and_logs_in(self):
        response = register(self.client, self.email)
        self.assertEqual(response.status_code, 302)
        user = get_user_by_email(self.email)
        self.assertIsNotNone(user)
        self.assertNotEqual(user["password_hash"], "safe-password-123")
        self.assertTrue(user["password_hash"])
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_login_rejects_wrong_password(self):
        register(self.client, self.email)
        self.client.post("/logout", data={
            "csrf_token": re.search(
                rb'name="csrf_token" value="([^"]+)"', self.client.get("/").data
            ).group(1).decode()
        })
        login_page = self.client.get("/login")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', login_page.data).group(1).decode()
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": self.email,
            "password": "not-the-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"email address or password is incorrect", response.data)

    def test_health_records_are_isolated_between_accounts(self):
        first_client = app.test_client()
        second_client = app.test_client()
        first_email = "first-{}@example.com".format(uuid.uuid4().hex)
        second_email = "second-{}@example.com".format(uuid.uuid4().hex)
        self.assertEqual(register(first_client, first_email).status_code, 302)
        first_client.post("/health/add", data={
            "date": date.today().isoformat(),
            "weight": "73.5",
            "water": "",
            "sleep": "",
            "steps": "",
            "calories": "",
        })
        self.assertIn(b"73.5", first_client.get("/health").data)

        self.assertEqual(register(second_client, second_email).status_code, 302)
        self.assertNotIn(b"73.5", second_client.get("/health").data)


class LoginFlowTests(unittest.TestCase):
    """The login page, session and logout are wired into the whole app."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.email = "flow-{}@example.com".format(uuid.uuid4().hex)

    def test_pages_redirect_to_login_when_logged_out(self):
        for path in ("/", "/health", "/health/nutrition", "/bmi", "/health/export"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login?next=", response.headers["Location"], path)

    def test_login_and_register_pages_are_public(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_login_success_returns_to_requested_page(self):
        register(self.client, self.email)
        logout(self.client)
        response = login(self.client, self.email, next_url="/health")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/health"))
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_login_ignores_external_next_url(self):
        register(self.client, self.email)
        logout(self.client)
        response = login(self.client, self.email, next_url="https://evil.example.com/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response.headers["Location"])

    def test_every_page_shows_account_strip_and_logout(self):
        register(self.client, self.email)
        for path in ("/", "/health", "/health/nutrition", "/bmi"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertIn(b"Signed in as", page.data, path)
            self.assertIn(b'action="/logout"', page.data, path)

    def test_welcome_message_is_shown_after_login(self):
        register(self.client, self.email)
        logout(self.client)
        login(self.client, self.email)
        self.assertIn(b"Welcome back, NutriCare Test.", self.client.get("/").data)

    def test_logout_ends_session(self):
        register(self.client, self.email)
        response = logout(self.client)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.client.get("/health").status_code, 302)

    def test_logout_requires_valid_token(self):
        register(self.client, self.email)
        self.client.post("/logout", data={"csrf_token": "wrong"})
        # Even a bad token logs the user out safely rather than staying signed in.
        self.assertEqual(self.client.get("/health").status_code, 302)

    def test_logged_in_user_visiting_login_goes_home(self):
        register(self.client, self.email)
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 302)

    def test_duplicate_email_is_rejected(self):
        register(self.client, self.email)
        logout(self.client)
        response = register(self.client, self.email.upper())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"already exists", response.data)

    def test_stale_session_for_missing_user_is_cleared(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 987654321
            sess["display_name"] = "Ghost"
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        # The login page must load (no redirect loop back to home).
        self.assertEqual(self.client.get("/login").status_code, 200)

    def test_api_returns_401_json_when_logged_out(self):
        response = self.client.post("/nutrition/analyze", json={"quantity_g": 100})
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.get_json())

    def test_api_works_when_logged_in(self):
        register(self.client, self.email)
        response = self.client.post("/nutrition/analyze", json={"quantity_g": 100, "sodium": 200})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["limit_crossed"])
        self.assertEqual(response.get_json()["checks"], [])


class PerUserDataTests(unittest.TestCase):
    """One user can never read, change or delete another user's records."""

    def setUp(self):
        app.config["TESTING"] = True
        self.alice = app.test_client()
        self.bob = app.test_client()
        register(self.alice, "alice-{}@example.com".format(uuid.uuid4().hex))
        register(self.bob, "bob-{}@example.com".format(uuid.uuid4().hex))
        self.today = date.today().isoformat()

    def _log(self, client, weight):
        return client.post("/health/add", data={"date": self.today, "weight": weight})

    def test_two_users_can_log_the_same_day(self):
        self.assertEqual(self._log(self.alice, "61.2").status_code, 302)
        self.assertEqual(self._log(self.bob, "88.8").status_code, 302)
        self.assertIn(b"61.2", self.alice.get("/health").data)
        self.assertNotIn(b"88.8", self.alice.get("/health").data)

    def test_cannot_edit_or_delete_other_users_log(self):
        self._log(self.alice, "61.2")
        log_id = re.search(rb'/health/edit/(\d+)', self.alice.get("/health").data).group(1).decode()
        edit = self.bob.post("/health/edit/" + log_id, data={"date": self.today, "weight": "99"})
        self.assertEqual(edit.status_code, 404)
        self.bob.post("/health/delete/" + log_id)
        self.assertIn(b"61.2", self.alice.get("/health").data)

    def test_csv_export_only_contains_own_logs(self):
        self._log(self.alice, "61.2")
        self._log(self.bob, "88.8")
        export = self.bob.get("/health/export").data
        self.assertIn(b"88.8", export)
        self.assertNotIn(b"61.2", export)

    def test_nutrition_entries_are_private(self):
        response = self.alice.post("/health/nutrition/add", data={
            "food_name": "Alice Secret Snack", "food_type": "packaged", "entry_date": self.today,
            "quantity_g": "50", "label_basis": "100g", "calories": "400",
            "protein": "8", "ingredients": "oats, peanuts, salt",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Alice Secret Snack", self.alice.get("/health/nutrition").data)
        self.assertNotIn(b"Alice Secret Snack", self.bob.get("/health/nutrition").data)

    def test_manual_meal_without_photo_shows_all_nutrients_and_ingredients(self):
        response = self.alice.post("/health/nutrition/add", data={
            "food_name": "Home lunch", "food_type": "homemade", "entry_date": self.today,
            "quantity_g": "250", "label_basis": "100g", "calories": "180",
            "protein": "7", "carbs": "28", "fat": "4", "sodium": "320",
            "ingredients": "rice, lentils, tomato",
            "cost_rupees": "99", "source": "should be ignored",
        })
        self.assertEqual(response.status_code, 302)
        with self.alice.session_transaction() as client_session:
            user_id = client_session["user_id"]
        with app.app_context():
            saved_entries = entries_on(self.today, user_id)
        self.assertIsNone(saved_entries[0]["cost_rupees"])
        self.assertIsNone(saved_entries[0]["source"])

        page = self.alice.get("/health/nutrition")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Home lunch", page.data)
        self.assertIn(b"rice, lentils, tomato", page.data)
        self.assertIn(b"View ingredients and all nutrients", page.data)
        self.assertIn(b"Protein", page.data)
        self.assertIn(b"Calories", page.data)
        self.assertIn(b"history-nutrient", page.data)
        self.assertIn(b"vitamin_b12", page.data)
        self.assertNotIn(b'name="cost_rupees"', page.data)
        self.assertNotIn(b'name="source"', page.data)
        self.assertIn(b"choose a clear photo", page.data)
        self.assertIn(b"Today's nutrition so far", page.data)

        historical_day = "2026-11-23"
        historical = self.alice.get("/health/nutrition?date=" + historical_day)
        self.assertIn(("Nutrition for " + historical_day).encode(), historical.data)


if __name__ == "__main__":
    unittest.main()
