from database import get_db_connection

DEFAULT_DISEASE_NUTRIENTS = (
    ("diabetes", "added_sugar", 25.0, "g"),
    ("diabetes", "carbs", 45.0, "g"),
    ("diabetes", "sodium", 600.0, "mg"),
    ("hypertension", "sodium", 400.0, "mg"),
    ("heart_disease", "saturated_fat", 5.0, "g"),
    ("heart_disease", "sodium", 600.0, "mg"),
    ("heart_disease", "sugar", 25.0, "g"),
    ("kidney_disease", "sodium", 400.0, "mg"),
    ("kidney_disease", "potassium", 350.0, "mg"),
    ("kidney_disease", "protein", 25.0, "g"),
)


def seed_default_disease_nutrients():
    """Insert default disease limits without overwriting existing values."""
    connection = get_db_connection()
    try:
        connection.executemany(
            """
            INSERT OR IGNORE INTO disease_nutrients
                (disease, nutrient, min_value, max_value, unit, age_group, gender)
            VALUES (?, ?, NULL, ?, ?, NULL, NULL)
            """,
            DEFAULT_DISEASE_NUTRIENTS,
        )
        connection.commit()
    finally:
        connection.close()
