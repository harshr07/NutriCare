from flask import Flask, jsonify, render_template, request
from health import health_bp
from nutrition_dashboard import nutrition_bp
from database import initialize_database, get_disease_nutrients


app = Flask(__name__, static_folder="statics")

initialize_database()

app.register_blueprint(health_bp)
app.register_blueprint(nutrition_bp)


# Homepage
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/calories", methods=["GET", "POST"])
def calorie_calculator():
    calories = None
    error = None
    goal = None

    if request.method == "POST":
        try:
            age = int(request.form["age"])
            weight = float(request.form["weight"])
            height = float(request.form["height"])
            sex = request.form["sex"]
            activity = float(request.form["activity"])
            goal = request.form["goal"]

            if age < 18 or age > 100 or weight <= 0 or height <= 0:
                error = "Please enter valid details."
            elif sex not in ("male", "female") or activity not in (1.2, 1.375, 1.55, 1.725) or goal not in ("lose", "maintain", "gain"):
                error = "Please select valid options."
            else:
                if sex == "male":
                    bmr = 10 * weight + 6.25 * height - 5 * age + 5
                else:
                    bmr = 10 * weight + 6.25 * height - 5 * age - 161

                calories = round(bmr * activity)

        except (ValueError, KeyError):
            error = "Please check your information and try again."

    return render_template(
        "calories.html",
        calories=calories,
        error=error,
        goal=goal
    )

@app.route("/bmi", methods=["GET", "POST"])
def bmi_calculator():
    bmi = None
    category = None
    error = None

    if request.method == "POST":
        try:
            weight = float(request.form["weight"])
            height = float(request.form["height"])

            if weight <= 0 or height <= 0:
                error = "Please enter valid measurements."
            else:
                height_m = height / 100
                bmi = round(weight / (height_m * height_m), 2)

                if bmi < 18.5:
                    category = "Underweight"
                elif bmi < 25:
                    category = "Healthy Weight"
                elif bmi < 30:
                    category = "Overweight"
                else:
                    category = "Obesity"

        except (ValueError, KeyError):
            error = "Please enter valid numbers."

    return render_template(
        "bmi.html",
        bmi=bmi,
        category=category,
        error=error
    )


# Backend nutrition suitability and portion analysis. Frontend integration is intentionally separate.
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
    if value < 0:
        raise ValueError("%s cannot be negative" % name)
    return value


@app.route("/nutrition/analyze", methods=["POST"])
def analyze_nutrition():
    """Analyze one consumed portion from packet/label values and a user's health constraints."""
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

                nutrient_limit_names = {
                    "calories_kcal": "calories", "protein_g": "protein", "carbs_g": "carbs",
                    "fat_g": "fat", "saturated_fat_g": "saturated_fat", "fiber_g": "fiber",
                    "sugar_g": "sugar", "added_sugar_g": "added_sugar", "sodium_mg": "sodium",
                    "potassium_mg": "potassium",
                }
                for limit_key, limit in constraints["limits"].items():
                    nutrient_key = nutrient_limit_names[limit_key]
                    value = consumed.get(nutrient_key)
                    if value is not None and value > limit:
                        warnings.append("%s exceeds the portion limit: %.2f > %.2f" % (limit_key, value, limit))
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
    data = request.get_json()
    food_items = data.get("food_items")
    portion_size = data.get("portion_size")

    # Here you would add the logic for analyzing the nutrition based on the food items
    # and portion size. This is just a placeholder for demonstration purposes.

    analysis = {
        "suitable_for_disease": True,  # Placeholder value
        "nutrients": {
            "calories": 250,  # Placeholder value
            "protein": 10,    # Placeholder value
            "fat": 5,         # Placeholder value
            "carbohydrates": 35  # Placeholder value
        }
    }

    return jsonify(analysis)


if __name__ == "__main__":
    app.run(debug=True)