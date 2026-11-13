"""NutriCare Health Tracker - local prototype only (authentication not connected)."""
import csv
import io
import os
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, redirect, render_template, request, url_for
from analytics import analyze_health

health_bp = Blueprint("health", __name__)


def get_db():
    os.makedirs(current_app.instance_path, exist_ok=True)
    database_path = os.path.join(current_app.instance_path, "health.db")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS health_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT UNIQUE NOT NULL,
        weight REAL, water REAL, sleep REAL, steps INTEGER,
        calories INTEGER
    )""")
    connection.commit()
    return connection


def number(form, name, minimum, maximum, integer=False):
    raw = form.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ValueError(f"Enter a valid number for {name}.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name.capitalize()} must be between {minimum} and {maximum}.")
    return value


def read_form(form):
    day = form.get("date", "")
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise ValueError("Enter a valid date.")
    if parsed > date.today():
        raise ValueError("Future dates are not allowed.")
    values = {
        "date": day,
        "weight": number(form, "weight", 1, 500),
        "water": number(form, "water", 0, 20),
        "sleep": number(form, "sleep", 0, 24),
        "steps": number(form, "steps", 0, 100000, integer=True),
        "calories": number(form, "calories", 0, 20000, integer=True),
    }
    if all(values[key] is None for key in ("weight", "water", "sleep", "steps", "calories")):
        raise ValueError("Add at least one measurement.")
    return values


@health_bp.route("/health")
def dashboard():
    days = 30 if request.args.get("days") == "30" else 7
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    db = get_db()
    rows = db.execute("SELECT * FROM health_logs WHERE log_date >= ? ORDER BY log_date", (start,)).fetchall()
    db.close()
    records = [{"id": r["id"], "date": r["log_date"], "weight": r["weight"],
                "water": r["water"], "sleep": r["sleep"], "steps": r["steps"],
                "calories": r["calories"]} for r in rows]
    stats = analyze_health(records)
    return render_template("health.html", records=records, stats=stats,
                           days=days, today=date.today().isoformat())


@health_bp.route("/health/add", methods=["POST"])
def save_health_log():
    try:
        values = read_form(request.form)
    except ValueError as error:
        return str(error), 400
    db = get_db()
    try:
        db.execute("""INSERT INTO health_logs
            (log_date, weight, water, sleep, steps, calories)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (values["date"], values["weight"], values["water"], values["sleep"], values["steps"], values["calories"]))
        db.commit()
    except sqlite3.IntegrityError:
        return "A log already exists for this date. Edit it below instead.", 400
    finally:
        db.close()
    return redirect(url_for("health.dashboard"))


@health_bp.route("/health/edit/<int:log_id>", methods=["POST"])
def update_health_log(log_id):
    try:
        values = read_form(request.form)
    except ValueError as error:
        return str(error), 400
    db = get_db()
    try:
        result = db.execute("""UPDATE health_logs SET log_date=?, weight=?, water=?, sleep=?, steps=?, calories=?
            WHERE id=?""", (values["date"], values["weight"], values["water"], values["sleep"], values["steps"], values["calories"], log_id))
        db.commit()
        if result.rowcount == 0:
            abort(404)
    except sqlite3.IntegrityError:
        return "Another log already exists for that date.", 400
    finally:
        db.close()
    return redirect(url_for("health.dashboard"))


@health_bp.route("/health/delete/<int:log_id>", methods=["POST"])
def delete_health_log(log_id):
    db = get_db()
    db.execute("DELETE FROM health_logs WHERE id=?", (log_id,))
    db.commit()
    db.close()
    return redirect(url_for("health.dashboard"))


@health_bp.route("/health/export")
def export_health_data():
    db = get_db()
    rows = db.execute("SELECT log_date, weight, water, sleep, steps, calories FROM health_logs ORDER BY log_date").fetchall()
    db.close()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "weight_kg", "water_liters", "sleep_hours", "steps", "calories_consumed"])
    writer.writerows([tuple(row) for row in rows])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=health_logs.csv"})
