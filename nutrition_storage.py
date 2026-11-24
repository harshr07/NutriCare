import os
import sqlite3
from flask import current_app


NUTRIENTS = {
    "calories": ("Calories", "kcal"),
    "protein": ("Protein", "g"),
    "carbs": ("Carbohydrates", "g"),
    "fat": ("Total fat", "g"),
    "saturated_fat": ("Saturated fat", "g"),
    "fiber": ("Fiber", "g"),
    "sugar": ("Total sugars", "g"),
    "added_sugar": ("Added sugars", "g"),
    "sodium": ("Sodium", "mg"),
    "potassium": ("Potassium", "mg"),
    "calcium": ("Calcium", "mg"),
    "iron": ("Iron", "mg"),
    "vitamin_a": ("Vitamin A (RAE)", "µg"),
    "vitamin_c": ("Vitamin C", "mg"),
    "vitamin_d": ("Vitamin D", "µg"),
    "vitamin_b12": ("Vitamin B12", "µg"),
}


def get_connection():
    os.makedirs(current_app.instance_path, exist_ok=True)
    path = os.path.join(current_app.instance_path, "health.db")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    columns = ", ".join(f"{name} REAL" for name in NUTRIENTS)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS nutrition_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            entry_date TEXT NOT NULL,
            food_name TEXT NOT NULL,
            food_type TEXT NOT NULL,
            ingredients TEXT,
            source TEXT,
            quantity_g REAL NOT NULL,
            label_basis TEXT NOT NULL,
            serving_g REAL,
            cost_rupees REAL,
            {columns}
        )
    """)
    columns_present = {row["name"] for row in db.execute("PRAGMA table_info(nutrition_entries)")}
    if "user_id" not in columns_present:
        # Preserve legacy rows, but keep them outside every newly registered user's view.
        db.execute("ALTER TABLE nutrition_entries ADD COLUMN user_id INTEGER")
    db.execute("CREATE INDEX IF NOT EXISTS idx_nutrition_entries_user_date ON nutrition_entries(user_id, entry_date)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_profiles (
            user_id INTEGER PRIMARY KEY,
            disease TEXT NOT NULL,
            gender TEXT NOT NULL,
            age INTEGER NOT NULL,
            body_weight_kg REAL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    return db


def get_profile(user_id):
    db = get_connection()
    try:
        row = db.execute("SELECT disease, gender, age, body_weight_kg FROM nutrition_profiles WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def save_profile(user_id, profile):
    db = get_connection()
    try:
        db.execute("""
            INSERT INTO nutrition_profiles (user_id, disease, gender, age, body_weight_kg)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                disease = excluded.disease,
                gender = excluded.gender,
                age = excluded.age,
                body_weight_kg = excluded.body_weight_kg,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, profile["disease"], profile["gender"], profile["age"], profile["body_weight_kg"]))
        db.commit()
    finally:
        db.close()


def latest_weight(user_id):
    db = get_connection()
    try:
        row = db.execute(
            "SELECT weight FROM health_logs WHERE user_id = ? AND weight IS NOT NULL ORDER BY log_date DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return row["weight"] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        db.close()


def save_entry(entry, user_id):
    fields = ["user_id", "entry_date", "food_name", "food_type", "ingredients", "source",
              "quantity_g", "label_basis", "serving_g", "cost_rupees"] + list(NUTRIENTS)
    placeholders = ", ".join("?" for _ in fields)
    with_db = get_connection()
    try:
        with_db.execute(
            f"INSERT INTO nutrition_entries ({', '.join(fields)}) VALUES ({placeholders})",
            [user_id] + [entry.get(name) for name in fields if name != "user_id"],
        )
        with_db.commit()
    finally:
        with_db.close()


def entries_on(day, user_id):
    db = get_connection()
    try:
        rows = db.execute(
            "SELECT * FROM nutrition_entries WHERE user_id = ? AND entry_date = ? ORDER BY id DESC",
            (user_id, day),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def entries_from(start, end, user_id):
    db = get_connection()
    try:
        rows = db.execute(
            "SELECT * FROM nutrition_entries WHERE user_id = ? AND entry_date BETWEEN ? AND ? ORDER BY entry_date",
            (user_id, start, end),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def remove_entry(entry_id, user_id):
    db = get_connection()
    try:
        db.execute("DELETE FROM nutrition_entries WHERE id = ? AND user_id = ?", (entry_id, user_id))
        db.commit()
    finally:
        db.close()
