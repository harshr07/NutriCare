import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from auth import auth_bp, current_user
from database import INSTANCE_DIR, initialize_database
from disease_nutrients import sync_disease_nutrients_from_csv
from food_safety import food_safety_bp, initialize_food_safety_db
from health import health_bp
from health_check import health_check_bp
from nutrition_analysis import nutrition_analysis_bp
from nutrition_dashboard import nutrition_bp


# Share one instance folder with database.py so every SQLite file lives together.
app = Flask(__name__, static_folder="statics", instance_path=str(INSTANCE_DIR))

# Use an environment-provided secret in deployed environments. For local use,
# create one persistent random secret in instance/ so sessions survive restarts.
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
secret_file = Path(app.instance_path) / ".flask_secret_key"
secret_key = os.environ.get("NUTRICARE_SECRET_KEY")
if not secret_key:
    if secret_file.exists():
        secret_key = secret_file.read_text(encoding="utf-8").strip()
    else:
        secret_key = secrets.token_urlsafe(48)
        secret_file.write_text(secret_key, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("NUTRICARE_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

initialize_database()
sync_disease_nutrients_from_csv()
with app.app_context():
    initialize_food_safety_db()

app.register_blueprint(auth_bp)
app.register_blueprint(health_bp)
app.register_blueprint(health_check_bp)
app.register_blueprint(nutrition_analysis_bp)
app.register_blueprint(nutrition_bp)
app.register_blueprint(food_safety_bp)


# JSON endpoints answer with a 401 instead of redirecting to the HTML login page.
API_ENDPOINTS = {
    "nutrition_analysis.analyze_nutrition",
    "nutrition_analysis.analyze_legacy_nutrition",
    "food_safety.analyze_food_label_route",
}


@app.before_request
def require_login():
    """Require a valid login for every application page and API endpoint."""
    public_endpoints = {"auth.login", "auth.register", "static"}
    if request.endpoint in public_endpoints:
        return None

    # current_user() also checks the account still exists, so a session left
    # over from a deleted account or a reset database is cleared.
    if current_user() is None:
        if request.endpoint in API_ENDPOINTS:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        requested = request.full_path if request.query_string else request.path
        if request.method != "GET":
            # A form that posted after the session expired; return to its page.
            requested = None
        return redirect(url_for("auth.login", next=requested))

    return None


@app.context_processor
def inject_account_details():
    user = current_user()
    return {
        "logged_in_user": user["full_name"] if user else session.get("display_name"),
        "logged_in_email": user["email"] if user else session.get("email"),
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.errorhandler(401)
def unauthorized(_error):
    flash("Please log in to continue.", "error")
    return redirect(url_for("auth.login"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
