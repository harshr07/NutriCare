import math

from flask import Blueprint, jsonify, request

from database import get_disease_nutrients

nutrition_analysis_bp = Blueprint("nutrition_analysis", __name__)

DISEASE_RULES = {
    "diabetes": {
        "restricted_ingredients": ("added sugar", "high fructose corn syrup", "glucose syrup"),
        "reason": "For diabetes, limit added sugar and total carbohydrates.",
    },
    "hypertension": {
        "restricted_ingredients": ("monosodium glutamate", "msg", "salt"),
        "reason": "For hypertension, keep sodium low.",
    },
    "heart_disease": {
        "restricted_ingredients": ("hydrogenated oil", "partially hydrogenated oil", "trans fat"),
        "reason": "For heart disease, limit saturated fat, trans fat, sodium, and added sugar.",
    },
    "kidney_disease": {
        "restricted_ingredients": ("phosphate", "potassium chloride"),
        "reason": "For kidney disease, monitor sodium, potassium, and protein.",
    },
}

ALLERGEN_INGREDIENTS = {
    "sugar": ("sugar", "sucrose", "cane sugar", "brown sugar", "dextrose", "fructose"),
    "gluten": ("wheat", "barley", "rye", "malt", "gluten", "atta", "maida"),
    "milk": ("milk", "milk solids", "whey", "casein", "cream", "butter"),
    "peanut": ("peanut", "groundnut"),
    "soy": ("soy", "soya", "soybean", "lecithin"),
}

NUTRIENT_FIELDS = (
    "calories", "protein", "carbs", "fat", "saturated_fat", "fiber",
    "sugar", "added_sugar", "sodium", "potassium", "calcium", "iron",
    "vitamin_a", "vitamin_c", "vitamin_d", "vitamin_b12",
)


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


def normalize_allergies(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def scaled_nutrients(payload, scale):
    nutrients = {}
    for field in NUTRIENT_FIELDS:
        value = parse_non_negative_number(payload, "%s_per_label" % field)
        if value is None:
            value = parse_non_negative_number(payload, field)
        nutrients[field] = round(value * scale, 3) if value is not None else None
    return nutrients


def assess_ingredients(ingredients, allergies, disease):
    warnings = []
    detected_allergens = []
    suitable = True

    for allergen in allergies:
        terms = ALLERGEN_INGREDIENTS.get(allergen, (allergen,))
        if any(term in ingredients for term in terms):
            detected_allergens.append(allergen)

    if detected_allergens:
        warnings.append("Allergen detected: %s" % ", ".join(detected_allergens))
        suitable = False

    disease_rule = DISEASE_RULES.get(disease)
    if disease_rule:
        restricted = [
            term for term in disease_rule["restricted_ingredients"]
            if term in ingredients
        ]
        if restricted:
            warnings.append("Restricted ingredient detected: %s" % ", ".join(restricted))
            suitable = False
        warnings.insert(0, disease_rule["reason"])
    elif disease:
        warnings.append("Unknown disease constraint; no disease-specific rule applied.")

    return detected_allergens, warnings, suitable


def assess_nutrient_limits(disease, nutrients):
    warnings = []
    suitable = True

    for row in get_disease_nutrients(disease):
        nutrient = str(row["nutrient"])
        value = nutrients.get(nutrient)
        maximum = row["max_value"]
        if value is None or maximum is None or value <= float(maximum):
            continue

        unit = row["unit"] or ""
        warnings.append("%s exceeds the portion limit: %.2f > %.2f %s" % (
            nutrient, value, float(maximum), unit
        ))
        suitable = False

    return warnings, suitable


def analyze_payload(payload):
    disease = str(payload.get("disease", "")).strip().lower().replace(" ", "_")
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

    nutrients = scaled_nutrients(payload, scale)
    ingredients = str(payload.get("ingredients", "")).lower()
    allergies = normalize_allergies(payload.get("allergies", []))
    detected_allergens, warnings, suitable = assess_ingredients(ingredients, allergies, disease)

    if disease in DISEASE_RULES:
        limit_warnings, within_limits = assess_nutrient_limits(disease, nutrients)
        warnings.extend(limit_warnings)
        suitable = suitable and within_limits

    return {
        "suitable": suitable,
        "status": "suitable" if suitable else "unsuitable",
        "disease": disease or None,
        "allergens_detected": detected_allergens,
        "warnings": warnings,
        "quantity_g": quantity_g,
        "consumed_nutrients": nutrients,
        "note": "This is a basic rule-based estimate, not medical advice.",
    }


def json_payload():
    return request.get_json(silent=True) or request.form.to_dict()


def legacy_payload(payload):
    compatible_payload = dict(payload)
    compatible_payload["quantity_g"] = payload.get("portion_size_g", payload.get("quantity_g"))
    if payload.get("food_items") and not payload.get("ingredients"):
        compatible_payload["ingredients"] = ", ".join(str(item) for item in payload["food_items"])
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
