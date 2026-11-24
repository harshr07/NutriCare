import re
import unittest
import uuid
from datetime import date, timedelta

import support
from support import register
from app import app
from daily_limits import available_conditions

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
FLASH = re.compile(r'<p class="flash error">([^<]+)</p>')
ROW = re.compile(r'<li class="limit-row (\w+)">\s*<div class="limit-head"><strong>([^<]+)</strong>')


class DailyLimitTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        register(self.client, "limits-{}@example.com".format(uuid.uuid4().hex))

    def set_condition(self, disease="diabetes", gender="male", age="30", weight=""):
        return self.client.post("/health/nutrition/profile", data={
            "disease": disease, "gender": gender, "age": age, "body_weight_kg": weight,
        })

    def add_meal(self, day=TODAY, **nutrients):
        data = {
            "food_name": "Test food", "entry_date": day, "food_type": "homemade",
            "quantity_g": "100", "label_basis": "100g",
        }
        data.update({name: str(value) for name, value in nutrients.items()})
        return self.client.post("/health/nutrition/add", data=data, follow_redirects=True)

    def page(self, day=TODAY):
        return self.client.get("/health/nutrition?date=" + day).get_data(as_text=True)

    def rows(self, html):
        return {name: state for state, name in ROW.findall(html)}


class ConditionFormTests(DailyLimitTests):
    def test_conditions_come_from_the_database(self):
        values = [item["value"] for item in available_conditions()]
        self.assertEqual(values[0], "healthy")
        for expected in ("diabetes", "chronic kidney disease", "fever"):
            self.assertIn(expected, values)

    def test_page_asks_for_condition_until_one_is_saved(self):
        html = self.page()
        self.assertIn("Choose it first", html)
        self.assertNotIn('class="limit-row', html)

    def test_saved_condition_is_shown(self):
        self.assertEqual(self.set_condition().status_code, 302)
        html = self.page()
        self.assertIn("Daily limits checked for", html)
        self.assertNotIn("Choose it first", html)

    def test_invalid_profiles_are_rejected(self):
        self.assertEqual(self.set_condition(disease="made-up").status_code, 400)
        self.assertEqual(self.set_condition(gender="other").status_code, 400)
        self.assertEqual(self.set_condition(age="abc").status_code, 400)
        self.assertEqual(self.set_condition(age="200").status_code, 400)
        self.assertEqual(self.set_condition(weight="5").status_code, 400)
        self.assertIn("Choose it first", self.page())

    def test_condition_is_private_to_each_account(self):
        self.set_condition()
        other = app.test_client()
        register(other, "other-{}@example.com".format(uuid.uuid4().hex))
        self.assertIn("Choose it first", other.get("/health/nutrition").get_data(as_text=True))


class WarningTests(DailyLimitTests):
    def setUp(self):
        super().setUp()
        self.set_condition("diabetes", "male", "30")

    def test_crossing_a_limit_shows_flash_and_alert(self):
        html = self.add_meal(sodium=2500).get_data(as_text=True)
        messages = FLASH.findall(html)
        self.assertEqual(len(messages), 1)
        self.assertIn("Sodium", messages[0])
        self.assertIn("Daily limit crossed", html)
        self.assertEqual(self.rows(html)["Sodium"], "over")

    def test_staying_within_limits_shows_no_warning(self):
        html = self.add_meal(sodium=500).get_data(as_text=True)
        self.assertEqual(FLASH.findall(html), [])
        self.assertNotIn("Daily limit crossed", html)
        self.assertEqual(self.rows(html)["Sodium"], "ok")

    def test_limits_use_the_whole_day_not_one_meal(self):
        first = self.add_meal(sodium=1500).get_data(as_text=True)
        self.assertEqual(FLASH.findall(first), [])
        second = self.add_meal(sodium=1000).get_data(as_text=True)
        self.assertEqual(len(FLASH.findall(second)), 1)

    def test_adding_more_of_an_exceeded_nutrient_warns_again(self):
        self.add_meal(sodium=2500)
        again = self.add_meal(sodium=100).get_data(as_text=True)
        self.assertEqual(len(FLASH.findall(again)), 1)

    def test_meal_without_the_exceeded_nutrient_does_not_warn_again(self):
        self.add_meal(sodium=2500)
        html = self.add_meal(protein=5).get_data(as_text=True)
        self.assertEqual(FLASH.findall(html), [])
        self.assertIn("Daily limit crossed", html)

    def test_each_day_is_checked_separately(self):
        self.add_meal(day=YESTERDAY, sodium=2000)
        html = self.add_meal(day=TODAY, sodium=2000).get_data(as_text=True)
        self.assertEqual(FLASH.findall(html), [])
        self.assertNotEqual(self.rows(html)["Sodium"], "over")

    def test_close_to_limit_is_marked(self):
        html = self.add_meal(calories=1900).get_data(as_text=True)
        self.assertEqual(self.rows(html)["Calories"], "near")

    def test_nutrients_never_logged_are_not_checked(self):
        html = self.add_meal(sodium=500).get_data(as_text=True)
        self.assertNotIn("Calories", self.rows(html))

    def test_minimum_is_a_goal_today_but_low_on_a_finished_day(self):
        self.set_condition("healthy", "male", "30")
        today = self.add_meal(day=TODAY, protein=10).get_data(as_text=True)
        self.assertEqual(self.rows(today)["Protein"], "building")
        self.add_meal(day=YESTERDAY, protein=10)
        self.assertEqual(self.rows(self.page(YESTERDAY))["Protein"], "low")


class BodyWeightTests(DailyLimitTests):
    def test_kidney_protein_limit_asks_for_weight(self):
        self.set_condition("chronic kidney disease", "male", "40")
        html = self.add_meal(protein=60).get_data(as_text=True)
        self.assertIn("your body weight", html)
        self.assertNotIn("Protein", self.rows(html))

    def test_kidney_protein_limit_uses_entered_weight(self):
        self.set_condition("chronic kidney disease", "male", "40", weight="50")
        html = self.add_meal(protein=60).get_data(as_text=True)
        self.assertEqual(self.rows(html)["Protein"], "over")

    def test_weight_from_health_tracker_is_used_when_blank(self):
        self.client.post("/health/add", data={"date": TODAY, "weight": "50"})
        self.set_condition("chronic kidney disease", "male", "40")
        html = self.add_meal(protein=60).get_data(as_text=True)
        self.assertEqual(self.rows(html)["Protein"], "over")


if __name__ == "__main__":
    unittest.main()
