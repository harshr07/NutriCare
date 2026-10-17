from flask import Flask, render_template, request

app = Flask(__name__)


# Homepage
@app.route("/")
def home():
    return render_template("index.html")


# BMI calculator
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
                error = "Please enter valid height and weight."

            else:
                height = height / 100

                bmi = round(weight / (height * height), 2)

                if bmi < 18.5:
                    category = "Underweight"
                elif bmi < 25:
                    category = "Healthy Weight"
                elif bmi < 30:
                    category = "Overweight"
                else:
                    category = "Obesity"

        except ValueError:
            error = "Please enter numbers only."

    return render_template(
        "bmi.html",
        bmi=bmi,
        category=category,
        error=error
    )


if __name__ == "__main__":
    app.run(debug=True)