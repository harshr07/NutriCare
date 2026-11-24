
import json
import re
import secrets
from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, request, session, url_for

from nutrition_storage import get_connection


DATA_PATH = (
    Path(__file__).resolve().parent
    / "datasets"
    / "json"
    / "food_safety_rules.json"
)

with open(DATA_PATH, encoding="utf-8") as file:
    DATA = json.load(file)

FOOD_SAFETY_DISEASES = DATA["diseases"]
ALIASES = DATA["ingredient_aliases"]

food_safety_bp = Blueprint("food_safety", __name__)


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def phrase_in(text, phrase):
    text = normalize(text)
    phrase = normalize(phrase)

    if not text or not phrase:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def parse_label_sections(raw_text):
    patterns = {
        "ingredients": r"\bingredients?(?:\s+list)?\s*:?\s+",
        "contains": r"\bcontains\s*:?\s+",
        "may_contain": r"\bmay\s+contain(?:\s+traces?\s+of)?\s*:?\s+"
    }

    markers = []

    for key, pattern in patterns.items():
        match = re.search(pattern, raw_text, re.I)
        if match:
            markers.append((key, match))

    markers.sort(key=lambda item: item[1].start())

    stop_pattern = re.compile(
        r"\b(?:nutrition facts|nutrition information|nutritional information|"
        r"best before|expiry date|manufactured by|net weight|mrp|fssai|"
        r"storage instructions)\b",
        re.I
    )

    sections = {
        "ingredients": "",
        "contains": "",
        "may_contain": ""
    }

    for index, (key, match) in enumerate(markers):
        start = match.end()
        end = len(raw_text)

        if index + 1 < len(markers):
            end = min(end, markers[index + 1][1].start())

        stop = stop_pattern.search(raw_text, start)
        if stop:
            end = min(end, stop.start())

        sections[key] = re.sub(
            r"\s+", " ", raw_text[start:end]
        ).strip(" :;\n\t-")

    return sections


def find_canonical_matches(text):
    found = set()

    for canonical, aliases in ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if phrase_in(text, alias):
                # Do not mistake "wheat starch" for ordinary wheat flour.
                if canonical == "wheat" and phrase_in(text, "wheat starch"):
                    continue

                found.add(canonical)
                break

    return found


ALLERGEN_GROUPS = {
    "milk", "peanut", "tree_nut", "soy",
    "egg", "fish", "crustacean", "sulphite"
}


def user_item_matches(item, text, found):
    item_name = normalize(item)

    for canonical, aliases in ALIASES.items():
        alias_names = {normalize(alias) for alias in aliases}

        if item_name == normalize(canonical) or item_name in alias_names:
            if canonical in ALLERGEN_GROUPS:
                return canonical in found

    # Custom preferences such as "palm oil" match that exact phrase.
    return phrase_in(text, item)


def split_items(value):
    values = re.split(r"[,;\n]", str(value or ""))

    return list(dict.fromkeys(
        item.strip()[:80]
        for item in values
        if item.strip()
    ))[:40]


def initialize_food_safety_db():
    db = get_connection()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS food_safety_diseases (
            disease_code TEXT PRIMARY KEY,
            disease_label TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS food_safety_aliases (
            alias TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            PRIMARY KEY (alias, canonical_key)
        );

        CREATE TABLE IF NOT EXISTS food_safety_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_code TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            source_id TEXT,
            source_url TEXT,
            review_status TEXT NOT NULL DEFAULT 'DRAFT',
            UNIQUE (disease_code, rule_type, item_key)
        );

        CREATE TABLE IF NOT EXISTS user_food_safety_profile (
            user_id INTEGER PRIMARY KEY,
            ckd_stage TEXT,
            on_dialysis INTEGER DEFAULT 0,
            potassium_restricted INTEGER DEFAULT 0,
            phosphorus_restricted INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_food_safety_diseases (
            user_id INTEGER NOT NULL,
            disease_code TEXT NOT NULL,
            PRIMARY KEY (user_id, disease_code)
        );

        CREATE TABLE IF NOT EXISTS user_food_safety_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_type TEXT NOT NULL,
            UNIQUE (user_id, item_name, item_type)
        );
    """)

    for disease in DATA["diseases"]:
        db.execute("""
            INSERT OR REPLACE INTO food_safety_diseases
            (disease_code, disease_label)
            VALUES (?, ?)
        """, (disease["code"], disease["label"]))

    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            db.execute("""
                INSERT OR IGNORE INTO food_safety_aliases
                (alias, canonical_key)
                VALUES (?, ?)
            """, (normalize(alias), canonical))

    for rule_type in ("ingredient_rules", "nutrient_rules"):
        for rule in DATA[rule_type]:
            source_url = DATA["sources"].get(rule["source"])

            item_key = rule.get(
                "ingredient_key", rule.get("nutrient")
            )

            db.execute("""
                INSERT OR REPLACE INTO food_safety_rules
                (disease_code, rule_type, item_key, status,
                 message, source_id, source_url, review_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule["disease"],
                rule_type,
                item_key,
                rule["status"],
                rule["message"],
                rule["source"],
                source_url,
                "DRAFT_NEEDS_CLINICAL_REVIEW"
            ))

    db.commit()
    db.close()


def legacy_disease_code(name):
    name = normalize(name)

    mapping = {
        "diabetes": "type2_diabetes",
        "type 2 diabetes": "type2_diabetes",
        "chronic kidney disease": "ckd",
        "kidney disease": "ckd",
        "hypertension": "hypertension",
        "celiac disease": "celiac_disease",
        "heart disease": "cardiovascular_disease"
    }

    return mapping.get(name)


def get_food_safety_preferences(user_id):
    db = get_connection()

    try:
        saved_profile = db.execute("""
            SELECT * FROM user_food_safety_profile
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        diseases = [
            row["disease_code"]
            for row in db.execute("""
                SELECT disease_code
                FROM user_food_safety_diseases
                WHERE user_id = ?
            """, (user_id,)).fetchall()
        ]

        items = db.execute("""
            SELECT item_name, item_type
            FROM user_food_safety_items
            WHERE user_id = ?
        """, (user_id,)).fetchall()

        # Preserve the old single-disease profile for existing users.
        if saved_profile is None:
            old = db.execute("""
                SELECT disease FROM nutrition_profiles
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if old:
                code = legacy_disease_code(old["disease"])
                if code:
                    diseases.append(code)

        return {
            "diseases": list(dict.fromkeys(diseases)),
            "avoid_ingredients": [
                row["item_name"] for row in items
                if row["item_type"] == "avoid"
            ],
            "allergies": [
                row["item_name"] for row in items
                if row["item_type"] == "allergy"
            ],
            "ckd_stage": saved_profile["ckd_stage"] if saved_profile else None,
            "on_dialysis": bool(saved_profile["on_dialysis"]) if saved_profile else False,
            "potassium_restricted": bool(saved_profile["potassium_restricted"]) if saved_profile else False,
            "phosphorus_restricted": bool(saved_profile["phosphorus_restricted"]) if saved_profile else False
        }

    finally:
        db.close()


def save_food_safety_preferences(user_id, form):
    allowed = {item["code"] for item in DATA["diseases"]}
    diseases = set(form.getlist("diseases"))

    if not diseases.issubset(allowed):
        raise ValueError("Invalid disease selection.")

    avoid = split_items(form.get("avoid_ingredients"))
    allergies = split_items(form.get("allergies"))

    ckd_stage = form.get("ckd_stage", "")
    if ckd_stage not in ("", "1", "2", "3a", "3b", "4", "5"):
        raise ValueError("Invalid CKD stage.")

    db = get_connection()

    try:
        db.execute("""
            INSERT OR REPLACE INTO user_food_safety_profile
            (user_id, ckd_stage, on_dialysis,
             potassium_restricted, phosphorus_restricted, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            ckd_stage or None,
            int(form.get("on_dialysis") == "1"),
            int(form.get("potassium_restricted") == "1"),
            int(form.get("phosphorus_restricted") == "1")
        ))

        db.execute(
            "DELETE FROM user_food_safety_diseases WHERE user_id = ?",
            (user_id,)
        )

        db.executemany("""
            INSERT INTO user_food_safety_diseases
            (user_id, disease_code)
            VALUES (?, ?)
        """, [(user_id, disease) for disease in diseases])

        db.execute(
            "DELETE FROM user_food_safety_items WHERE user_id = ?",
            (user_id,)
        )

        for item in avoid:
            db.execute("""
                INSERT INTO user_food_safety_items
                (user_id, item_name, item_type)
                VALUES (?, ?, 'avoid')
            """, (user_id, item))

        for item in allergies:
            db.execute("""
                INSERT INTO user_food_safety_items
                (user_id, item_name, item_type)
                VALUES (?, ?, 'allergy')
            """, (user_id, item))

        db.commit()

    finally:
        db.close()


def analyze_label_payload(data, preferences):
    raw_text = str(data.get("raw_label_text") or "")

    sections = parse_label_sections(raw_text)

    ingredients = str(
        data.get("ingredients") or sections["ingredients"]
    )

    contains = str(
        data.get("contains_text") or sections["contains"]
    )

    may_contain = str(
        data.get("may_contain_text") or sections["may_contain"]
    )

    ingredient_matches = find_canonical_matches(ingredients)
    contains_matches = find_canonical_matches(contains)
    may_matches = find_canonical_matches(may_contain)

    findings = []
    diseases = set(preferences.get("diseases", []))

    def add_finding(status, category, message, **extra):
        findings.append({
            "status": status,
            "category": category,
            "message": message,
            **extra
        })

    # Personal avoid list
    for item in preferences.get("avoid_ingredients", []):
        if (
            user_item_matches(item, ingredients, ingredient_matches)
            or user_item_matches(item, contains, contains_matches)
        ):
            add_finding(
                "AVOID", "PERSONAL_PREFERENCE",
                f"{item} is in your personal avoid list.",
                ingredient=item
            )

        elif user_item_matches(item, may_contain, may_matches):
            add_finding(
                "CONDITIONAL", "PERSONAL_PREFERENCE",
                f"The packet may contain {item}, which is on your avoid list.",
                ingredient=item
            )

    # Personal allergies
    for item in preferences.get("allergies", []):
        if (
            user_item_matches(item, ingredients, ingredient_matches)
            or user_item_matches(item, contains, contains_matches)
        ):
            add_finding(
                "AVOID", "PERSONAL_ALLERGY",
                f"Your declared allergen {item} was detected.",
                ingredient=item
            )

        elif user_item_matches(item, may_contain, may_matches):
            add_finding(
                "CONDITIONAL", "PERSONAL_ALLERGY",
                f"Possible cross-contact with your allergen {item} is declared.",
                ingredient=item
            )

    # Disease-specific ingredient rules
    for rule in DATA["ingredient_rules"]:
        if rule["disease"] not in diseases:
            continue

        key = rule["ingredient_key"]
        status = rule["status"]

        present = (
            key in ingredient_matches
            or key in contains_matches
        )
        possible = key in may_matches

        if not present and not possible:
            continue

        if possible:
            status = "CONDITIONAL"

        add_finding(
            status,
            "DISEASE_INGREDIENT_RULE",
            rule["message"],
            disease=rule["disease"],
            ingredient_key=key,
            source_url=DATA["sources"].get(rule["source"])
        )

    # Validate serving size and calculate consumed nutrient amounts
    try:
        quantity = float(data.get("quantity_g"))
        if not 0 < quantity <= 10000:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Enter a valid quantity eaten in grams.")

    basis = data.get("label_basis", "100g")
    if basis not in ("100g", "serving"):
        raise ValueError("Invalid nutrition label basis.")

    if basis == "serving":
        try:
            serving = float(data.get("serving_g"))
            if not 0 < serving <= 10000:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Enter a valid serving size.")

        factor = quantity / serving
    else:
        factor = quantity / 100

    consumed = {}

    for nutrient, raw_value in (data.get("nutrition") or {}).items():
        if raw_value in (None, ""):
            continue

        try:
            value = float(raw_value)
            if not 0 <= value <= 100000:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {nutrient}.")

        consumed[nutrient] = round(value * factor, 3)

    # Disease-specific nutrient rules
    for rule in DATA["nutrient_rules"]:
        if rule["disease"] not in diseases:
            continue

        nutrient = rule["nutrient"]

        if nutrient not in consumed:
            continue

        message = rule["message"]

        if rule["disease"] == "ckd":
            if nutrient == "potassium" and not preferences["potassium_restricted"]:
                message += " This is only a restriction if advised by your clinician."

            if nutrient == "phosphorus" and not preferences["phosphorus_restricted"]:
                message += " This is only a restriction if advised by your clinician."

            if nutrient == "protein":
                message += " Dialysis status and kidney stage affect protein needs."

        finding = {
            "status": rule["status"],
            "category": "NUTRIENT_RULE",
            "disease": rule["disease"],
            "nutrient": nutrient,
            "amount": consumed[nutrient],
            "unit": rule["unit"],
            "message": message,
            "source_url": DATA["sources"].get(rule["source"])
        }

        if rule.get("reference_value"):
            finding["reference_value"] = rule["reference_value"]
            finding["reference_unit"] = rule["reference_unit"]
            finding["reference_percent"] = round(
                consumed[nutrient] / rule["reference_value"] * 100, 1
            )

        findings.append(finding)

    priority = {
        "AVOID": 5,
        "LIMIT": 4,
        "CONDITIONAL": 3,
        "TRACK": 2
    }

    overall = (
        max(findings, key=lambda item: priority.get(item["status"], 0))["status"]
        if findings else "NO_CONFIGURED_RULE"
    )

    return {
        "overall_status": overall,
        "findings": findings,
        "extracted_sections": {
            "ingredients": ingredients,
            "contains": contains,
            "may_contain": may_contain
        },
        "consumed_nutrients": consumed,
        "review_required": not bool(ingredients.strip()),
        "notice": (
            "No configured warning does not prove that a product is safe. "
            "Verify the original packet and all OCR values."
        ),
        "dataset_review_status": DATA["metadata"]["review_status"]
    }


def valid_csrf(token):
    expected = session.get("auth_csrf_token", "")
    return bool(token and expected and secrets.compare_digest(token, expected))


@food_safety_bp.route(
    "/health/nutrition/food-safety/profile",
    methods=["POST"]
)
def save_food_safety_profile_route():
    # Keep the day the user was viewing and return to the same profile panel
    # for both successful and rejected submissions.
    return_url = url_for(
        "nutrition.dashboard", date=request.form.get("date") or None
    ) + "#food-safety-profile"

    if not valid_csrf(request.form.get("csrf_token", "")):
        flash("Form expired. Please try again.", "error")
        return redirect(return_url)

    try:
        save_food_safety_preferences(
            session["user_id"], request.form
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(return_url)

    flash("Your food safety preferences have been saved.", "success")
    return redirect(return_url)


@food_safety_bp.route(
    "/health/nutrition/food-safety/analyze",
    methods=["POST"]
)
def analyze_food_label_route():
    data = request.get_json(silent=True) or {}

    if not valid_csrf(data.get("csrf_token", "")):
        return jsonify({"error": "Invalid or expired form token."}), 400

    try:
        preferences = get_food_safety_preferences(session["user_id"])
        result = analyze_label_payload(data, preferences)
        return jsonify(result)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
