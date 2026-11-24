"""Tests for CSV-backed disease nutrient limits."""

import unittest
import uuid
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import support as _support
from support import register
from app import app
import database
from database import get_disease_nutrients, initialize_database
from disease_nutrients import load_disease_nutrients, sync_disease_nutrients_from_csv


class CsvDiseaseLimitTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        register(self.client, "limits-{}@example.com".format(uuid.uuid4().hex))

    def analyze(self, **payload):
        return self.client.post("/nutrition/analyze", json=payload)

    def test_csv_rows_are_loaded_with_verification_and_demographics(self):
        source_rows = load_disease_nutrients()
        stored_rows = get_disease_nutrients()
        self.assertEqual(len(stored_rows), len(source_rows))
        self.assertTrue(any(row["verified"].lower() == "yes" for row in stored_rows))
        self.assertTrue(any(row["verified"].lower() == "no" for row in stored_rows))
        self.assertTrue(any(
            row["disease"] == "Healthy" and row["nutrient"] == "Protein"
            and row["gender"] == "Male" for row in stored_rows
        ))

    def test_existing_database_schema_migrates_and_csv_replaces_old_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            with patch.object(database, "INSTANCE_DIR", Path(temp_dir)), patch.object(
                database, "DATABASE", database_path
            ):
                connection = sqlite3.connect(database_path)
                connection.execute("""
                    CREATE TABLE disease_nutrients (
                        disease TEXT NOT NULL,
                        nutrient TEXT NOT NULL,
                        min_value REAL,
                        max_value REAL,
                        unit TEXT,
                        age_group TEXT,
                        gender TEXT,
                        PRIMARY KEY (disease, nutrient)
                    )
                """)
                connection.execute(
                    "INSERT INTO disease_nutrients (disease, nutrient, max_value) VALUES (?, ?, ?)",
                    ("legacy-only", "sodium", 1),
                )
                connection.commit()
                connection.close()

                initialize_database()
                migrated = get_disease_nutrients("legacy-only")
                self.assertEqual(migrated[0]["verified"], "No")

                imported_count = sync_disease_nutrients_from_csv()
                self.assertEqual(len(get_disease_nutrients()), imported_count)
                self.assertEqual(get_disease_nutrients("legacy-only"), [])

    def test_verified_csv_maximum_reports_crossed_limit(self):
        response = self.analyze(
            disease="diabetes", age=35, gender="male", quantity_g=100,
            label_basis="100g", calories_per_label=2101,
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["limit_crossed"])
        self.assertEqual(result["status"], "limit_crossed")
        self.assertEqual(len(result["checks"]), 1)
        self.assertEqual(result["checks"][0]["nutrient"], "calories")
        self.assertEqual(result["checks"][0]["maximum"], 2000)
        self.assertEqual(result["checks"][0]["status"], "above_maximum")

    def test_csv_minimum_can_be_reported_without_calling_it_an_upper_limit_crossing(self):
        response = self.analyze(
            disease="Healthy", age=35, gender="male", quantity_g=100,
            label_basis="100g", protein_per_label=20,
        )
        result = response.get_json()
        self.assertEqual(result["status"], "below_minimum")
        self.assertFalse(result["limit_crossed"])
        self.assertEqual(result["checks"][0]["minimum"], 43)

    def test_unverified_csv_rows_are_not_used_as_limits(self):
        response = self.analyze(
            disease="diabetes", age=35, gender="female", quantity_g=100,
            label_basis="100g", vitamin_c_per_label=5000,
        )
        result = response.get_json()
        self.assertEqual(result["status"], "no_verified_limits")
        self.assertEqual(result["checks"], [])
        self.assertFalse(result["limit_crossed"])

    def test_disease_without_verified_csv_limits_has_no_fallback_rules(self):
        response = self.analyze(
            disease="hypertension", age=35, gender="male", quantity_g=100,
            label_basis="100g", sodium_per_label=100000,
            ingredients="salt, monosodium glutamate", allergies=["soy"],
        )
        result = response.get_json()
        self.assertEqual(result["status"], "no_verified_limits")
        self.assertEqual(result["checks"], [])
        self.assertFalse(result["limit_crossed"])

    def test_demographic_specific_csv_limit_requires_profile(self):
        response = self.analyze(
            disease="diabetes", age=35, quantity_g=100,
            label_basis="100g", protein_per_label=75,
        )
        result = response.get_json()
        self.assertEqual(result["status"], "profile_required")
        self.assertIn("gender", result["profile_required"])
        self.assertEqual(result["checks"], [])

    def test_ckd_alias_uses_verified_weight_based_protein_limit(self):
        response = self.analyze(
            disease="kidney_disease", age=40, gender="female", body_weight_kg=60,
            quantity_g=100, label_basis="100g", protein_per_label=50,
        )
        result = response.get_json()
        self.assertEqual(result["disease"], "chronic kidney disease")
        protein = next(check for check in result["checks"] if check["nutrient"] == "Protein")
        self.assertEqual(protein["maximum"], 48)
        self.assertEqual(protein["unit"], "g/day")
        self.assertEqual(protein["status"], "above_maximum")

    def test_ingredient_or_allergy_text_does_not_create_non_csv_flags(self):
        response = self.analyze(
            disease="diabetes", age=35, gender="female", quantity_g=100,
            label_basis="100g", ingredients="wheat, added sugar", allergies=["gluten"],
        )
        result = response.get_json()
        self.assertEqual(set(result), {
            "limit_crossed", "status", "disease", "checks", "profile_required", "source",
        })
        self.assertFalse(result["limit_crossed"])
        self.assertEqual(result["checks"], [])

    def test_serving_values_are_scaled_before_csv_comparison(self):
        response = self.analyze(
            disease="diabetes", age=35, gender="male", quantity_g=60,
            label_basis="serving", serving_g=30, calories_per_label=1100,
        )
        result = response.get_json()
        calories = next(check for check in result["checks"] if check["nutrient"] == "calories")
        self.assertEqual(calories["value"], 2200)
        self.assertEqual(calories["status"], "above_maximum")

    def test_vitamin_d_is_converted_to_csv_unit_before_comparison(self):
        response = self.analyze(
            disease="Healthy", age=35, gender="male", quantity_g=100,
            label_basis="100g", vitamin_d_per_label=101,
        )
        result = response.get_json()
        vitamin_d = next(check for check in result["checks"] if check["nutrient"] == "Vitamin D")
        self.assertEqual(vitamin_d["value"], 4040)
        self.assertEqual(vitamin_d["unit"], "IU/day")
        self.assertEqual(vitamin_d["status"], "above_maximum")


if __name__ == "__main__":
    unittest.main()
