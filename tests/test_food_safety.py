import unittest

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


if __name__ == "__main__":
    unittest.main()
