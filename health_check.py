import math

from flask import Blueprint, render_template, request

health_check_bp = Blueprint("health_check", __name__)


@health_check_bp.route("/bmi", methods=["GET", "POST"])
@health_check_bp.route("/calories", methods=["GET", "POST"])
def health_check():
    bmi = None
    category = None
    error = None
    health = None

    if request.method == "POST":
        try:
            weight = float(request.form["weight"])
            height = float(request.form["height"])

            if not math.isfinite(weight) or not math.isfinite(height) or weight <= 0 or height <= 0:
                raise ValueError("Please enter valid measurements.")

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

            age_raw = request.form.get("age", "").strip()
            sex = request.form.get("sex", "").strip()
            activity_raw = request.form.get("activity", "").strip()
            goal = request.form.get("goal", "maintain").strip()

            age = float(age_raw) if age_raw else None
            activity = float(activity_raw) if activity_raw else None

            if age_raw and (age is None or not math.isfinite(age) or age < 18 or age > 100):
                raise ValueError("Please enter a valid age between 18 and 100.")
            if activity_raw and (activity is None or not math.isfinite(activity) or activity < 1 or activity > 2.5):
                raise ValueError("Please select a valid activity level.")
            if goal not in ("lose", "maintain", "gain"):
                raise ValueError("Please select a valid weight goal.")

            tdee = None
            calorie_goal = None
            if age is not None and sex in ("male", "female") and activity is not None:
                bmr = 10 * weight + 6.25 * height - 5 * age
                bmr += 5 if sex == "male" else -161
                tdee = round(bmr * activity)
                adjustment = -300 if goal == "lose" else (300 if goal == "gain" else 0)
                calorie_goal = max(1200, tdee + adjustment)

            if activity is None:
                steps_goal = 8000
            elif activity < 1.375:
                steps_goal = 6000
            elif activity < 1.55:
                steps_goal = 8000
            elif activity < 1.725:
                steps_goal = 10000
            else:
                steps_goal = 12000

            if goal == "lose" and bmi >= 25:
                guidance = "Aim for gradual, sustainable weight loss with a modest calorie deficit."
            elif goal == "gain" and bmi < 18.5:
                guidance = "Aim for gradual, nutritious weight gain with regular meals and strength activity."
            elif category == "Underweight":
                guidance = "Focus on nutrient-dense foods and consult a health professional if weight loss is unintended."
            elif category == "Obesity":
                guidance = "Small sustainable changes in activity and nutrition can improve health risk."
            else:
                guidance = "Maintain balanced meals, regular movement and consistent sleep."

            health = {
                "tdee": tdee,
                "calorie_goal": calorie_goal,
                "water_liters": round(weight * 0.035, 1),
                "steps_goal": steps_goal,
                "sleep_goal": "7–9 hours",
                "healthy_weight_min": round(18.5 * height_m * height_m, 1),
                "healthy_weight_max": round(24.9 * height_m * height_m, 1),
                "guidance": guidance,
            }

        except (ValueError, KeyError) as exc:
            error = str(exc) if str(exc).startswith("Please") else "Please enter valid numbers."

    return render_template(
        "health_check.html",
        bmi=bmi,
        category=category,
        health=health,
        error=error,
    )
