import math
import re

from flask import Blueprint, jsonify, request

from database import get_disease_nutrients

nutrition_analysis_bp = Blueprint("nutrition_analysis", __name__)

DISEASE_ALIASES = {
    "ckd": "chronic kidney disease",
    "kidney disease": "chronic kidney disease",
    "chronic kidney disease": "chronic kidney disease",
}

NUTRIENT_ALIASES = {
    "energy": "calories",
    "calories": "calories",
    "carbohydrate": "carbs",
    "carbohydrates": "carbs",
    "total sugar": "sugar",
    "total sugars": "sugar",
    "fluid": "water",
    "vitamin b1 thiamine": "vitamin_b1_thiamine",
    "vitamin b2 riboflavin": "vitamin_b2_riboflavin",
}

NUTRIENT_UNITS = {
    "calories": "kcal", "energy": "kcal", "protein": "g",
    "carbohydrate": "g", "carbohydrates": "g", "total sugar": "g",
    "sodium": "mg", "potassium": "mg", "calcium": "mg", "iron": "mg",
    "zinc": "mg", "magnesium": "mg", "iodine": "µg", "folate": "µg",
    "vitamin a": "µg", "vitamin b6": "mg", "vitamin b12": "µg",
    "vitamin b1 thiamine": "mg", "vitamin b2 riboflavin": "mg",
    "vitamin c": "mg", "vitamin d": "µg", "cinnamon": "g", "fluid": "L",
    "water": "L", "vitamin_b1_thiamine": "mg", "vitamin_b2_riboflavin": "mg",
}


class NutritionAnalysisError(ValueError):
    """Invalid nutrition-analysis payload."""


def parse_non_negative_number(payload, field_name):
    raw_value = payload.get(field_name)
    if raw_value in (None, ""):
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise NutritionAnalysisError("%s must be a number" % field_name) from exc

    if not math.isfinite(value) or value < 0:
        raise NutritionAnalysisError("%s must be a finite non-negative number" % field_name)
    return value


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_unit(value):
    unit = str(value or "").strip().lower()
    unit = unit.replace("μ", "µ").replace("mcg", "µg")
    unit = re.sub(r"\s*(/\s*day|per\s+day)$", "", unit)
    return re.sub(r"\s+", "", unit)


def nutrient_field(nutrient):
    normalized = normalize_name(nutrient)
    if normalized in NUTRIENT_ALIASES:
        return NUTRIENT_ALIASES[normalized]
    return normalized.replace(" ", "_")


def read_nutrient_value(payload, nutrient, scale, target_unit):
    field = nutrient_field(nutrient)
    value = parse_non_negative_number(payload, "%s_per_label" % field)
    if value is None:
        value = parse_non_negative_number(payload, field)
    if value is None:
        return None

    source_unit = payload.get("%s_unit" % field) or NUTRIENT_UNITS.get(normalize_name(nutrient))
    return convert_nutrient_unit(value * scale, source_unit, target_unit, nutrient)


def convert_nutrient_unit(value, source_unit, target_unit, nutrient):
    if not source_unit:
        return value

    source = normalize_unit(source_unit)
    target = normalize_unit(target_unit)
    if target.startswith("g/kg"):
        target = "g"
    if source == target:
        return value
    if source == "g" and target == "mg":
        return value * 1000
    if source == "mg" and target == "g":
        return value / 1000
    if source in ("µg", "ug") and target == "mg":
        return value / 1000
    if source == "mg" and target in ("µg", "ug"):
        return value * 1000
    if normalize_name(nutrient) == "vitamin d" and source == "µg" and target == "iu":
        return value * 40
    if normalize_name(nutrient) == "vitamin d" and source == "iu" and target == "µg":
        return value / 40
    return value


def evaluate_limits(payload, disease, scale):
    rows = [
        row for row in get_disease_nutrients(verified_only=True)
        if normalize_name(row["disease"]) == disease
    ]
    checks = []
    profile_required = set()

    age_group = normalize_name(payload.get("age_group"))
    if not age_group and payload.get("age") not in (None, ""):
        age = parse_non_negative_number(payload, "age")
        age_group = "adult" if age is not None and age >= 18 else "under 18"
    gender = normalize_name(payload.get("gender"))

    grouped_rows = {}
    for row in rows:
        if row["min_value"] is None and row["max_value"] is None:
            continue
        key = (normalize_name(row["nutrient"]), normalize_unit(row["unit"]))
        grouped_rows.setdefault(key, []).append(row)

    for nutrient_rows in grouped_rows.values():
        first = nutrient_rows[0]
        nutrient = str(first["nutrient"])
        unit = first["unit"] or ""
        value = read_nutrient_value(payload, nutrient, scale, unit)
        if value is None:
            continue

        available_age_groups = {
            normalize_name(row["age_group"]) for row in nutrient_rows if row["age_group"]
        }
        if available_age_groups:
            if not age_group:
                profile_required.add("age")
                continue
            nutrient_rows = [
                row for row in nutrient_rows
                if not row["age_group"] or normalize_name(row["age_group"]) == age_group
            ]
            if not nutrient_rows:
                continue

        gender_rows = [row for row in nutrient_rows if row["gender"]]
        if gender and gender_rows:
            nutrient_rows = [
                row for row in nutrient_rows
                if not row["gender"] or normalize_name(row["gender"]) == gender
            ]
            if not nutrient_rows:
                continue
        elif not gender and gender_rows:
            bounds = {
                (row["min_value"], row["max_value"])
                for row in gender_rows
            }
            genders = {normalize_name(row["gender"]) for row in gender_rows}
            if len(bounds) > 1 or genders != {"male", "female"}:
                profile_required.add("gender")
                continue
            nutrient_rows = [gender_rows[0]]

        row = nutrient_rows[0]
        minimum = row["min_value"]
        maximum = row["max_value"]
        if normalize_unit(unit) == "g/kgbodyweight":
            body_weight = parse_non_negative_number(payload, "body_weight_kg")
            if body_weight is None:
                profile_required.add("body_weight_kg")
                continue
            minimum = minimum * body_weight if minimum is not None else None
            maximum = maximum * body_weight if maximum is not None else None
            unit = "g/day"

        above_maximum = maximum is not None and value > maximum
        below_minimum = minimum is not None and value < minimum
        status = "above_maximum" if above_maximum else "below_minimum" if below_minimum else "within_range"
        checks.append({
            "nutrient": nutrient,
            "value": round(value, 3),
            "minimum": minimum,
            "maximum": maximum,
            "unit": unit,
            "age_group": row["age_group"],
            "gender": row["gender"],
            "status": status,
            "limit_crossed": above_maximum,
        })

    return checks, sorted(profile_required)


def analyze_payload(payload):
    disease = normalize_name(payload.get("disease"))
    disease = DISEASE_ALIASES.get(disease, disease)
    quantity_g = parse_non_negative_number(payload, "quantity_g")
    label_basis = str(payload.get("label_basis", "100g")).strip().lower()
    serving_g = parse_non_negative_number(payload, "serving_g")

    if quantity_g is None:
        raise NutritionAnalysisError("quantity_g is required")
    if quantity_g == 0:
        raise NutritionAnalysisError("quantity_g must be greater than zero")
    if label_basis not in ("100g", "serving"):
        raise NutritionAnalysisError("label_basis must be 100g or serving")
    if label_basis == "serving":
        if serving_g is None or serving_g == 0:
            raise NutritionAnalysisError("serving_g is required when label_basis is serving")
        scale = quantity_g / serving_g
    else:
        scale = quantity_g / 100.0

    checks, profile_required = evaluate_limits(payload, disease, scale)
    crossed_limits = any(check["limit_crossed"] for check in checks)
    below_minimum = any(check["status"] == "below_minimum" for check in checks)
    if checks:
        status = "limit_crossed" if crossed_limits else "below_minimum" if below_minimum else "within_limits"
    else:
        status = "profile_required" if profile_required else "no_verified_limits"
    return {
        "limit_crossed": crossed_limits,
        "status": status,
        "disease": disease or None,
        "checks": checks,
        "profile_required": profile_required,
        "source": "datasets/csv/overall_disease_nutrition.csv (verified rows only)",
    }


def json_payload():
    return request.get_json(silent=True) or request.form.to_dict()


def legacy_payload(payload):
    compatible_payload = dict(payload)
    compatible_payload["quantity_g"] = payload.get("portion_size_g", payload.get("quantity_g"))
    compatible_payload.setdefault("label_basis", "100g")
    return compatible_payload


def analysis_response(payload):
    try:
        return jsonify(analyze_payload(payload))
    except NutritionAnalysisError as exc:
        return jsonify({"error": str(exc)}), 400


@nutrition_analysis_bp.route("/nutrition/analyze", methods=["POST"])
def analyze_nutrition():
    return analysis_response(json_payload())


@nutrition_analysis_bp.route("/nutrition-analysis", methods=["POST"])
def analyze_legacy_nutrition():
    return analysis_response(legacy_payload(json_payload()))
