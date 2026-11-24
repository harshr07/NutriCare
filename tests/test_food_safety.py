import unittest
import uuid
from datetime import date, timedelta

import support
from app import app
from support import register
from food_safety import analyze_label_payload, parse_label_sections


class FoodSafetyTests(unittest.TestCase):
    def profile(self, disease, allergies=None):
        return {
            "diseases": [disease],
            "avoid_ingredients": [],
            "allergies": allergies or [],
            "potassium_restricted": False,
            "phosphorus_restricted": False,
        }

    def payload(self, **extra):
        return {
            "raw_label_text": "",
            "ingredients": "",
            "contains_text": "",
            "may_contain_text": "",
            "quantity_g": 30,
            "label_basis": "100g",
            "serving_g": "",
            "nutrition": {},
            **extra,
        }

    def test_celiac_wheat(self):
        result = analyze_label_payload(
            self.payload(ingredients="Rice flour, wheat flour, salt"),
            self.profile("celiac_disease"),
        )
        self.assertEqual(result["overall_status"], "AVOID")

    def test_diabetes_sugar_is_limit_not_avoid(self):
        result = analyze_label_payload(
            self.payload(ingredients="Sugar, rice flour"),
            self.profile("type2_diabetes"),
        )
        self.assertEqual(result["overall_status"], "LIMIT")

    def test_personal_allergy_may_contain(self):
        result = analyze_label_payload(
            self.payload(may_contain_text="peanuts"),
            self.profile("type2_diabetes", allergies=["peanut"]),
        )
        self.assertEqual(result["overall_status"], "CONDITIONAL")

    def test_portion_scaling(self):
        result = analyze_label_payload(
            self.payload(nutrition={"sodium": 800}, quantity_g=30),
            self.profile("hypertension"),
        )
        self.assertEqual(result["consumed_nutrients"]["sodium"], 240)

    def test_ckd_potassium_is_conditional(self):
        result = analyze_label_payload(
            self.payload(ingredients="Rice flour, potassium chloride"),
            self.profile("ckd"),
        )
        self.assertEqual(result["overall_status"], "CONDITIONAL")

    def test_ingredients_section_parser(self):
        sections = parse_label_sections(
            "Ingredients: wheat flour, salt\n"
            "Contains: milk\n"
            "May contain traces of peanuts\n"
            "Nutrition Facts"
        )
        self.assertIn("wheat flour", sections["ingredients"])
        self.assertIn("milk", sections["contains"])
        self.assertIn("peanuts", sections["may_contain"])


class RedirectPreservationTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        register(self.client, "redirect-{}@example.com".format(uuid.uuid4().hex))

    def test_food_safety_profile_keeps_selected_nutrition_date(self):
        selected_day = (date.today() - timedelta(days=1)).isoformat()
        token = support.csrf_token(
            self.client, "/health/nutrition?date=" + selected_day
        )
        response = self.client.post("/health/nutrition/food-safety/profile", data={
            "csrf_token": token,
            "date": selected_day,
            "diseases": ["celiac_disease"],
            "avoid_ingredients": "",
            "allergies": "",
            "ckd_stage": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/health/nutrition?date={0}#food-safety-profile".format(selected_day),
        )

    def test_health_log_keeps_selected_history_range(self):
        selected_day = (date.today() - timedelta(days=1)).isoformat()
        token = support.csrf_token(self.client, "/health?days=30")
        response = self.client.post("/health/add", data={
            "csrf_token": token,
            "date": selected_day,
            "weight": "65",
            "days": "30",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/health?days=30")


if __name__ == "__main__":
    unittest.main()
