from datetime import date, timedelta
import math
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from daily_limits import available_conditions, limit_report
from nutrition_analysis import normalize_name
from nutrition_storage import (
    NUTRIENTS, entries_from, entries_on, get_profile, latest_weight, remove_entry, save_entry, save_profile,
)

nutrition_bp = Blueprint("nutrition", __name__)

COMMON = ["calories", "protein", "carbs", "fat", "fiber", "sugar", "added_sugar", "saturated_fat", "sodium"]
EXTRA = [name for name in NUTRIENTS if name not in COMMON]


def selected_day():
    raw = request.values.get("date") or request.values.get("entry_date") or date.today().isoformat()
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        day = date.today()
    return min(day, date.today()).isoformat()


def optional_number(text, label):
    if text is None or text.strip() == "":
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"Enter a number for {label}.")
    if not math.isfinite(value) or not 0 <= value <= 100000:
        raise ValueError(f"Enter a valid non-negative value for {label}.")
    return value


def build_entry(form):
    name = form.get("food_name", "").strip()
    if not name or len(name) > 120:
        raise ValueError("Enter a food name (up to 120 characters).")

    food_type = form.get("food_type", "")
    if food_type not in ("packaged", "homemade"):
        raise ValueError("Select packaged or homemade food.")

    day = form.get("entry_date", "")
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise ValueError("Enter a valid date.")
    if parsed > date.today():
        raise ValueError("Future dates are not allowed.")

    quantity = optional_number(form.get("quantity_g"), "quantity eaten")
    if quantity is None or quantity <= 0 or quantity > 10000:
        raise ValueError("Enter a quantity between 0 and 10,000 g.")

    basis = form.get("label_basis", "100g")
    if basis not in ("100g", "serving"):
        raise ValueError("Choose whether the label is per 100 g or per serving.")
    serving = optional_number(form.get("serving_g"), "serving size")
    if basis == "serving" and (serving is None or serving <= 0 or serving > 10000):
        raise ValueError("Enter the serving size in grams from the label.")

    # Nutrition labels list values per 100 g or per serving, so scale to the actual amount eaten.
    factor = quantity / (100 if basis == "100g" else serving)

    entry = {
        "entry_date": day,
        "food_name": name,
        "food_type": food_type,
        "ingredients": form.get("ingredients", "").strip()[:500],
        "source": None,
        "quantity_g": quantity,
        "label_basis": basis,
        "serving_g": serving if basis == "serving" else None,
        "cost_rupees": None,
    }
    has_nutrition = False
    for field, (label, unit) in NUTRIENTS.items():
        value = optional_number(form.get(field), f"{label} ({unit})")
        if value is not None:
            has_nutrition = True
        entry[field] = round(value * factor, 3) if value is not None else None
    if not has_nutrition:
        raise ValueError("Enter at least one nutrient from the food label or database.")
    return entry


def build_profile(form):
    allowed = {item["value"] for item in available_conditions()}
    disease = normalize_name(form.get("disease"))
    if disease not in allowed:
        raise ValueError("Choose your health condition from the list.")

    gender = form.get("gender", "")
    if gender not in ("male", "female"):
        raise ValueError("Choose male or female so the right limits are used.")

    try:
        age = int(form.get("age", ""))
    except ValueError:
        raise ValueError("Enter your age in years.")
    if not 1 <= age <= 120:
        raise ValueError("Enter an age between 1 and 120.")

    weight = optional_number(form.get("body_weight_kg"), "body weight")
    if weight is not None and not 20 <= weight <= 400:
        raise ValueError("Enter a body weight between 20 and 400 kg.")

    return {"disease": disease, "gender": gender, "age": age, "body_weight_kg": weight}


def known_totals(entries):
    # If a nutrient was never supplied, keep it unknown rather than reporting zero.
    totals = {}
    for field in NUTRIENTS:
        values = [item[field] for item in entries if item[field] is not None]
        totals[field] = round(sum(values), 2) if values else None
    return totals


def report_for(records, day):
    user_id = session["user_id"]
    return limit_report(
        known_totals(records), get_profile(user_id), latest_weight(user_id), day < date.today().isoformat(),
    )


def exceeded_amounts(day):
    report = report_for(entries_on(day, session["user_id"]), day)
    if not report:
        return {}
    return {row["name"]: row for row in report["exceeded"]}


def dashboard_page(day, error=None, profile_error=None):
    records = entries_on(day, session["user_id"])
    today = date.today()
    start = today - timedelta(days=6)
    week_records = entries_from(start.isoformat(), today.isoformat(), session["user_id"])
    week = []
    for i in range(7):
        d = start + timedelta(days=i)
        daily = [entry for entry in week_records if entry["entry_date"] == d.isoformat()]
        week.append({"date": d.strftime("%a %d"), "nutrients": known_totals(daily)})
    return render_template(
        "nutrition_dashboard.html", records=records, totals=known_totals(records),
        nutrients=NUTRIENTS, common=COMMON, extra=EXTRA,
        selected_date=day, today=today.isoformat(), week=week, error=error,
        conditions=available_conditions(), profile=get_profile(session["user_id"]),
        saved_weight=latest_weight(session["user_id"]), profile_error=profile_error,
        limit_report=report_for(records, day),
    )


@nutrition_bp.route("/health/nutrition")
def dashboard():
    return dashboard_page(selected_day())


@nutrition_bp.route("/health/nutrition/add", methods=["POST"])
def add():
    try:
        entry = build_entry(request.form)
    except ValueError as exc:
        return dashboard_page(selected_day(), str(exc)), 400
    before = exceeded_amounts(entry["entry_date"])
    save_entry(entry, session["user_id"])
    for name, row in exceeded_amounts(entry["entry_date"]).items():
        if name not in before or row["amount"] > before[name]["amount"]:
            flash("Warning: {} is now {} {} for {}, over your daily limit ({}).".format(
                name, row["value"], row["unit"], entry["entry_date"], row["range_text"]), "error")
    return redirect(url_for("nutrition.dashboard", date=entry["entry_date"]))


@nutrition_bp.route("/health/nutrition/profile", methods=["POST"])
def save_condition():
    try:
        profile = build_profile(request.form)
    except ValueError as exc:
        return dashboard_page(selected_day(), profile_error=str(exc)), 400
    save_profile(session["user_id"], profile)
    flash("Your health condition was saved. Daily limits are checked every time you add a food.", "success")
    return redirect(url_for("nutrition.dashboard", date=selected_day()) + "#condition")


@nutrition_bp.route("/health/nutrition/delete/<int:entry_id>", methods=["POST"])
def delete(entry_id):
    remove_entry(entry_id, session["user_id"])
    return redirect(url_for("nutrition.dashboard", date=selected_day()))
