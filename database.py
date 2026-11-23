import os
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

# Store the main application database in the project's instance/ directory.
# NUTRICARE_INSTANCE_DIR can point somewhere else (the test suite uses a temp dir).
# app.py uses this same folder as Flask's instance_path, so the account database
# and the health/nutrition database always live side by side.
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = Path(os.environ.get("NUTRICARE_INSTANCE_DIR") or (BASE_DIR / "instance")).resolve()
DATABASE = INSTANCE_DIR / "nutricare_users.db"


def get_db_connection():
    """Open a connection to the NutriCare SQLite database."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    """Create the account and disease-nutrient tables if they do not exist."""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
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


def create_user(full_name, email, password):
    """Create a user account. Passwords are stored only as secure hashes."""
    password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
            (full_name, email.strip().lower(), password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    """Return a user row matching an email address, if one exists."""
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT id, full_name, email, password_hash FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return safe account details for a logged-in user."""
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT id, full_name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def verify_user_password(user, password):
    """Verify a submitted password against the account's stored hash."""
    return bool(user and check_password_hash(user["password_hash"], password))


def add_disease_nutrient(
    disease,
    nutrient,
    min_value=None,
    max_value=None,
    unit=None,
    age_group=None,
    gender=None,
):
    """Insert one disease/nutrient row."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO disease_nutrients
                (disease, nutrient, min_value, max_value, unit, age_group, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (disease, nutrient, min_value, max_value, unit, age_group, gender))
        conn.commit()
    finally:
        conn.close()


def get_disease_nutrients(disease=None):
    """Fetch all rows, or only rows matching a disease."""
    conn = get_db_connection()
    try:
        if disease is None:
            rows = conn.execute("""
                SELECT disease, nutrient, min_value, max_value, unit, age_group, gender
                FROM disease_nutrients ORDER BY disease, nutrient
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT disease, nutrient, min_value, max_value, unit, age_group, gender
                FROM disease_nutrients WHERE disease = ? ORDER BY nutrient
            """, (disease,)).fetchall()
        return rows
    finally:
        conn.close()


def delete_disease_nutrient(disease, nutrient):
    """Delete one row using its composite primary key."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM disease_nutrients WHERE disease = ? AND nutrient = ?",
            (disease, nutrient),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
