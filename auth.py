import re
import secrets
import sqlite3
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database import create_user, get_user_by_email, get_user_by_id, verify_user_password

auth_bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _safe_next_url(target):
    """Allow only local relative paths after authentication."""
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return None
    return target


def current_user():
    """Return the logged-in user's row, or None if the session is missing or stale.

    The result is cached on flask.g for the rest of the request. A session that
    points at an account which no longer exists is cleared.
    """
    if "current_user" in g:
        return g.current_user
    user = None
    user_id = session.get("user_id")
    if user_id:
        user = get_user_by_id(user_id)
        if user is None:
            session.clear()
    g.current_user = user
    return user


def _start_session(user_id, full_name, email):
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["display_name"] = full_name
    session["email"] = email
    g.current_user = get_user_by_id(user_id)


def _csrf_token():
    token = session.get("auth_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["auth_csrf_token"] = token
    return token


def _valid_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("auth_csrf_token", "")
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


@auth_bp.app_context_processor
def inject_auth_helpers():
    return {"auth_csrf_token": _csrf_token}


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
    if current_user():
        return redirect(next_url or url_for("home"))

    if request.method == "POST":
        if not _valid_csrf():
            flash("Your form session expired. Please try again.", "error")
            return render_template("register.html", next_url=next_url), 400

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not 2 <= len(full_name) <= 80:
            flash("Please enter your name (2 to 80 characters).", "error")
        elif len(email) > 254 or not EMAIL_PATTERN.match(email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Your password must contain at least 8 characters.", "error")
        elif len(password) > 128:
            flash("Your password must be 128 characters or fewer.", "error")
        elif password != confirm_password:
            flash("The passwords do not match.", "error")
        elif get_user_by_email(email):
            flash("An account with this email already exists. Please log in.", "error")
        else:
            try:
                user_id = create_user(full_name, email, password)
            except sqlite3.IntegrityError:
                # A concurrent registration may have claimed the same email.
                flash("An account with this email already exists. Please log in.", "error")
            else:
                _start_session(user_id, full_name, email)
                flash("Your NutriCare account has been created.", "success")
                return redirect(next_url or url_for("home"))

    return render_template("register.html", next_url=next_url)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
    if current_user():
        return redirect(next_url or url_for("home"))

    if request.method == "POST":
        if not _valid_csrf():
            flash("Your form session expired. Please try again.", "error")
            return render_template("login.html", next_url=next_url), 400

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_user_by_email(email) if email else None

        # Use the same message for unknown emails and incorrect passwords.
        if not verify_user_password(user, password):
            flash("The email address or password is incorrect.", "error")
        else:
            _start_session(user["id"], user["full_name"], user["email"])
            flash("Welcome back, {}.".format(user["full_name"]), "success")
            return redirect(next_url or url_for("home"))

    return render_template("login.html", next_url=next_url)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if not _valid_csrf():
        flash("Your logout form expired. Please log in again.", "error")
        session.clear()
        return redirect(url_for("auth.login"))
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
