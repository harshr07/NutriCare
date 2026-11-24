"""Unit tests for the BMI calculator in NutriCare."""

import unittest
import uuid

import support as _support  # noqa: F401  (sets test database before importing app)
from support import register
from app import app


class BMICalculatorTests(unittest.TestCase):
    """Check BMI calculations and input validation through Flask routes."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        # The health check is behind login, like every other app page.
        register(self.client, "bmi-{}@example.com".format(uuid.uuid4().hex))

    def test_requires_login(self):
        response = app.test_client().post("/bmi", data={"weight": "68", "height": "170"})
        self.assertEqual(response.status_code, 302)

    def test_healthy_weight_calculation(self):
        response = self.client.post(
            "/bmi", data={"weight": "68", "height": "170"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<strong>23.53</strong>", response.data)
        self.assertIn(b"Healthy Weight", response.data)

    def test_underweight_category(self):
        response = self.client.post(
            "/bmi", data={"weight": "45", "height": "170"}
        )
        self.assertIn(b"Underweight", response.data)

    def test_obesity_category(self):
        response = self.client.post(
            "/bmi", data={"weight": "95", "height": "170"}
        )
        self.assertIn(b"Obesity", response.data)

    def test_zero_weight_is_rejected(self):
        response = self.client.post(
            "/bmi", data={"weight": "0", "height": "170"}
        )
        self.assertIn(b"Please enter valid measurements.", response.data)
        self.assertNotIn(b"Body balance", response.data)

    def test_non_numeric_input_is_rejected(self):
        response = self.client.post(
            "/bmi", data={"weight": "abc", "height": "170"}
        )
        self.assertIn(b"Please enter valid numbers.", response.data)


if __name__ == "__main__":
    unittest.main()
