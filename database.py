import sqlite3
from pathlib import Path

# Store the database in the project's instance/ directory.
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE = INSTANCE_DIR / "nutricare_users.db"


def get_db_connection():
    """Open a connection to the NutriCare SQLite database."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    """
    Create the disease_nutrients table if it does not already exist.

    The combination of disease and nutrient is the composite primary key.
    The existing users table is left unchanged.
    """
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS disease_nutrients (
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
        conn.commit()
    finally:
        conn.close()


def add_disease_nutrient(
    disease,
    nutrient,
    min_value=None,
    max_value=None,
    unit=None,
    age_group=None,
    gender=None
):
    """Insert one disease/nutrient row."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO disease_nutrients
                (disease, nutrient, min_value, max_value, unit, age_group, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            disease, nutrient, min_value, max_value,
            unit, age_group, gender
        ))
        conn.commit()
    finally:
        conn.close()


def get_disease_nutrients(disease=None):
    """Fetch all rows, or only rows matching a disease."""
    conn = get_db_connection()
    try:
        if disease is None:
            rows = conn.execute("""
                SELECT disease, nutrient, min_value, max_value,
                       unit, age_group, gender
                FROM disease_nutrients
                ORDER BY disease, nutrient
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT disease, nutrient, min_value, max_value,
                       unit, age_group, gender
                FROM disease_nutrients
                WHERE disease = ?
                ORDER BY nutrient
            """, (disease,)).fetchall()

        return rows
    finally:
        conn.close()


def delete_disease_nutrient(disease, nutrient):
    """Delete one row using its composite primary key."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            DELETE FROM disease_nutrients
            WHERE disease = ? AND nutrient = ?
        """, (disease, nutrient))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()