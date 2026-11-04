from flask import Flask, render_template, request

app = Flask(__name__)


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

if __name__ == "__main__":
    app.run(debug=True)