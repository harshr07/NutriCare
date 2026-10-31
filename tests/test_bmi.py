"""Unit tests for the BMI calculator in NutriCare."""

import unittest

from app import app


class BMICalculatorTests(unittest.TestCase):
    """Check BMI calculations and input validation through Flask routes."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_healthy_weight_calculation(self):
        response = self.client.post(
            "/bmi", data={"weight": "68", "height": "170"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your BMI: 23.53", response.data)
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
        self.assertIn(b"Please enter valid height and weight.", response.data)
        self.assertNotIn(b"Your BMI:", response.data)

    def test_non_numeric_input_is_rejected(self):
        response = self.client.post(
            "/bmi", data={"weight": "abc", "height": "170"}
        )
        self.assertIn(b"Please enter numbers only.", response.data)


if __name__ == "__main__":
    unittest.main()
