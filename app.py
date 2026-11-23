from flask import Flask, jsonify, render_template, request
from database import initialize_database
from disease_nutrients import seed_default_disease_nutrients
from health import health_bp
from health_check import health_check_bp
from nutrition_analysis import nutrition_analysis_bp
from nutrition_dashboard import nutrition_bp


app = Flask(__name__, static_folder="statics")

initialize_database()
seed_default_disease_nutrients()

app.register_blueprint(health_bp)
app.register_blueprint(health_check_bp)
app.register_blueprint(nutrition_analysis_bp)
app.register_blueprint(nutrition_bp)


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)