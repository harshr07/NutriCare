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
    db.commit()
    return db


def save_entry(entry):
    fields = ["entry_date", "food_name", "food_type", "ingredients", "source",
              "quantity_g", "label_basis", "serving_g", "cost_rupees"] + list(NUTRIENTS)
    placeholders = ", ".join("?" for _ in fields)
    with_db = get_connection()
    try:
        with_db.execute(
            f"INSERT INTO nutrition_entries ({', '.join(fields)}) VALUES ({placeholders})",
            [entry.get(name) for name in fields],
        )
        with_db.commit()
    finally:
        with_db.close()


def entries_on(day):
    db = get_connection()
    try:
        rows = db.execute(
            "SELECT * FROM nutrition_entries WHERE entry_date = ? ORDER BY id DESC",
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def entries_from(start, end):
    db = get_connection()
    try:
        rows = db.execute(
            "SELECT * FROM nutrition_entries WHERE entry_date BETWEEN ? AND ? ORDER BY entry_date",
            (start, end),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def remove_entry(entry_id):
    db = get_connection()
    try:
        db.execute("DELETE FROM nutrition_entries WHERE id = ?", (entry_id,))
        db.commit()
    finally:
        db.close()
