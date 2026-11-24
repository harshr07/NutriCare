import os
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


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
        _migrate_disease_nutrients(conn)
        conn.commit()
    finally:
        conn.close()


def _create_disease_nutrients_table(conn, table_name="disease_nutrients"):
    conn.execute("""
        CREATE TABLE {} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease TEXT NOT NULL,
            nutrient TEXT NOT NULL,
            min_value REAL,
            max_value REAL,
            unit TEXT,
            age_group TEXT,
            gender TEXT,
            verified TEXT NOT NULL DEFAULT 'No'
        )
    """.format(table_name))


def _migrate_disease_nutrients(conn):
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("disease_nutrients",),
    ).fetchone()
    if table is None:
        _create_disease_nutrients_table(conn)
    else:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(disease_nutrients)")}
        has_surrogate_id = any(
            row["name"] == "id" and row["pk"] == 1
            for row in conn.execute("PRAGMA table_info(disease_nutrients)")
        )
        if "verified" not in columns or not has_surrogate_id:
            conn.execute("ALTER TABLE disease_nutrients RENAME TO disease_nutrients_legacy")
            _create_disease_nutrients_table(conn)
            legacy_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(disease_nutrients_legacy)")
            }
            verified_expression = "verified" if "verified" in legacy_columns else "'No'"
            conn.execute("""
                INSERT INTO disease_nutrients
                    (disease, nutrient, min_value, max_value, unit, age_group, gender, verified)
                SELECT disease, nutrient, min_value, max_value, unit, age_group, gender, {}
                FROM disease_nutrients_legacy
            """.format(verified_expression))
            conn.execute("DROP TABLE disease_nutrients_legacy")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_disease_nutrients_lookup
        ON disease_nutrients (disease, verified, age_group, gender)
    """)


def replace_disease_nutrients(rows):
    """Replace the stored dataset atomically with parsed CSV rows."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM disease_nutrients")
        conn.executemany("""
            INSERT INTO disease_nutrients
                (disease, nutrient, min_value, max_value, unit, age_group, gender, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
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
    verified="No",
):
    """Insert one disease/nutrient row, including its source verification status."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO disease_nutrients
                (disease, nutrient, min_value, max_value, unit, age_group, gender, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (disease, nutrient, min_value, max_value, unit, age_group, gender, verified))
        conn.commit()
    finally:
        conn.close()


def get_disease_nutrients(disease=None, verified_only=False):
    """Fetch dataset rows, optionally filtering by disease and verified source status."""
    conn = get_db_connection()
    try:
        query = """
            SELECT disease, nutrient, min_value, max_value, unit,
                   age_group, gender, verified
            FROM disease_nutrients
        """
        filters = []
        parameters = []
        if disease is not None:
            filters.append("LOWER(disease) = LOWER(?)")
            parameters.append(disease)
        if verified_only:
            filters.append("LOWER(verified) = 'yes'")
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY nutrient, age_group, gender"
        rows = conn.execute(query, parameters).fetchall()
        return rows
    finally:
        conn.close()


def delete_disease_nutrient(disease, nutrient):
    """Delete all rows for one disease/nutrient pair."""
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
