import math

from flask import Flask, jsonify, render_template, request
from health import health_bp
from health_check import health_check_bp
from nutrition_dashboard import nutrition_bp
from database import add_disease_nutrient, initialize_database, get_disease_nutrients


app = Flask(__name__, static_folder="statics")

initialize_database()

if not get_disease_nutrients():
    defaults = (
        ("diabetes", "added_sugar", None, 25.0, "g", None, None),
        ("diabetes", "carbs", None, 45.0, "g", None, None),
        ("diabetes", "sodium", None, 600.0, "mg", None, None),
        ("hypertension", "sodium", None, 400.0, "mg", None, None),
        ("heart_disease", "saturated_fat", None, 5.0, "g", None, None),
        ("heart_disease", "sodium", None, 600.0, "mg", None, None),
        ("heart_disease", "sugar", None, 25.0, "g", None, None),
        ("kidney_disease", "sodium", None, 400.0, "mg", None, None),
        ("kidney_disease", "potassium", None, 350.0, "mg", None, None),
        ("kidney_disease", "protein", None, 25.0, "g", None, None),
    )
    for disease, nutrient, minimum, maximum, unit, age_group, gender in defaults:
        add_disease_nutrient(disease, nutrient, minimum, maximum, unit, age_group, gender)

app.register_blueprint(health_bp)
app.register_blueprint(health_check_bp)
app.register_blueprint(nutrition_bp)


@app.route("/")
def home():
    return render_template("index.html")


DISEASE_CONSTRAINTS = {
    "diabetes": {
        "avoid_ingredients": ["added sugar", "high fructose corn syrup", "glucose syrup"],
        "limits": {"added_sugar_g": 25.0, "carbs_g": 45.0, "sodium_mg": 600.0},
        "reason": "For diabetes, limit added sugar and total carbohydrates.",
    },
    "hypertension": {
        "avoid_ingredients": ["monosodium glutamate", "msg", "salt"],
        "limits": {"sodium_mg": 400.0},
        "reason": "For hypertension, keep sodium low.",
    },
    "heart_disease": {
        "avoid_ingredients": ["hydrogenated oil", "partially hydrogenated oil", "trans fat"],
        "limits": {"saturated_fat_g": 5.0, "sodium_mg": 600.0, "sugar_g": 25.0},
        "reason": "For heart disease, limit saturated fat, trans fat, sodium, and added sugar.",
    },
    "kidney_disease": {
        "avoid_ingredients": ["phosphate", "potassium chloride"],
        "limits": {"sodium_mg": 400.0, "potassium_mg": 350.0, "protein_g": 25.0},
        "reason": "For kidney disease, monitor sodium, potassium, and protein.",
    },
}

INGREDIENT_ALIASES = {
    "sugar": ["sugar", "sucrose", "cane sugar", "brown sugar", "dextrose", "fructose"],
    "gluten": ["wheat", "barley", "rye", "malt", "gluten", "atta", "maida"],
    "milk": ["milk", "milk solids", "whey", "casein", "cream", "butter"],
    "peanut": ["peanut", "groundnut"],
    "soy": ["soy", "soya", "soybean", "lecithin"],
}


def positive_number(payload, name):
    value = payload.get(name)
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be a number" % name)
    if not math.isfinite(value) or value < 0:
        raise ValueError("%s must be a finite non-negative number" % name)
    return value


@app.route("/nutrition/analyze", methods=["POST"])
def analyze_nutrition():
    payload = request.get_json(silent=True) or request.form.to_dict()

    try:
        disease = str(payload.get("disease", "")).strip().lower().replace(" ", "_")
        allergies = payload.get("allergies", [])
        if isinstance(allergies, str):
            allergies = [item.strip().lower() for item in allergies.split(",") if item.strip()] 

        quantity_g = positive_number(payload, "quantity_g")
        label_basis = str(payload.get("label_basis", "100g")).lower()
        serving_g = positive_number(payload, "serving_g")

        if quantity_g is None:
            raise ValueError("quantity_g is required")
        if quantity_g == 0:
            raise ValueError("quantity_g must be greater than zero")
        if label_basis not in ("100g", "serving"):
            raise ValueError("label_basis must be 100g or serving")
        if label_basis == "serving":
            if not serving_g:
                raise ValueError("serving_g is required when label_basis is serving")
            scale = quantity_g / serving_g
        else:
            scale = quantity_g / 100.0

        nutrient_keys = (
            "calories", "protein", "carbs", "fat", "saturated_fat", "fiber",
            "sugar", "added_sugar", "sodium", "potassium", "calcium", "iron",
            "vitamin_a", "vitamin_c", "vitamin_d", "vitamin_b12",
        )
        consumed = {}
        for key in nutrient_keys:
            label_key = "%s_per_label" % key
            value = positive_number(payload, label_key)
            if value is None:
                value = positive_number(payload, key)
            consumed[key] = round(value * scale, 3) if value is not None else None

        ingredients = str(payload.get("ingredients", "")).lower()
        warnings = []
        suitability = "suitable"

        matched_allergens = []
        for allergy in allergies:
            allergy_key = str(allergy).strip().lower()
            terms = INGREDIENT_ALIASES.get(allergy_key, [allergy_key])
            if any(term in ingredients for term in terms):
                matched_allergens.append(allergy_key)
        if matched_allergens:
            warnings.append("Allergen detected: %s" % ", ".join(matched_allergens))
            suitability = "unsuitable"

        if disease:
            constraints = DISEASE_CONSTRAINTS.get(disease)
            if constraints:
                avoid_terms = constraints["avoid_ingredients"]
                detected = [term for term in avoid_terms if term in ingredients]
                if detected:
                    warnings.append("Restricted ingredient detected: %s" % ", ".join(detected))
                    suitability = "unsuitable"

                database_limits = get_disease_nutrients(disease)
                for limit_row in database_limits:
                    nutrient_key = str(limit_row["nutrient"])
                    maximum = limit_row["max_value"]
                    unit = limit_row["unit"]
                    value = consumed.get(nutrient_key)
                    if value is not None and maximum is not None and value > float(maximum):
                        warnings.append("%s exceeds the portion limit: %.2f > %.2f %s" % (
                            nutrient_key, value, float(maximum), unit or ""
                        ))
                        suitability = "unsuitable"

                warnings.insert(0, constraints["reason"])
            else:
                warnings.append("Unknown disease constraint; no disease-specific rule applied.")

        return jsonify({
            "suitable": suitability == "suitable",
            "status": suitability,
            "disease": disease or None,
            "allergens_detected": matched_allergens,
            "warnings": warnings,
            "quantity_g": quantity_g,
            "consumed_nutrients": consumed,
            "note": "This is a basic rule-based estimate, not medical advice.",
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/nutrition-analysis", methods=["POST"])
def nutrition_analysis():
    payload = request.get_json(silent=True) or {}
    payload["quantity_g"] = payload.get("portion_size_g", payload.get("quantity_g"))
    if payload.get("food_items") and not payload.get("ingredients"):
        payload["ingredients"] = ", ".join(str(item) for item in payload["food_items"])
    if payload.get("label_basis") is None:
        payload["label_basis"] = "100g"
    with app.test_request_context("/nutrition/analyze", method="POST", json=payload):
        return analyze_nutrition()


if __name__ == "__main__":
    app.run(debug=True)