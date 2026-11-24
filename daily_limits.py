from database import get_disease_nutrients
from nutrition_analysis import evaluate_limits, normalize_name

NEAR_LIMIT_PERCENT = 85
HEALTHY_LABEL = "Healthy (no specific condition)"
STATE_ORDER = {"over": 0, "near": 1, "low": 2, "building": 3, "ok": 4}
MISSING_PROFILE_TEXT = {
    "age": "your age",
    "gender": "your gender",
    "body_weight_kg": "your body weight",
}


def pretty_name(name):
    name = name.strip()
    return name.capitalize() if name == name.lower() else name


def condition_label(name):
    if normalize_name(name) == "healthy":
        return HEALTHY_LABEL
    return pretty_name(name)


def available_conditions():
    labels = {}
    for row in get_disease_nutrients(verified_only=True):
        if row["min_value"] is None and row["max_value"] is None:
            continue
        labels.setdefault(normalize_name(row["disease"]), condition_label(row["disease"]))
    ordered = sorted(labels.items(), key=lambda pair: (pair[0] != "healthy", pair[1]))
    return [{"value": value, "label": label} for value, label in ordered]


def number(value):
    return "{:g}".format(round(value, 1))


def range_text(minimum, maximum, unit):
    if minimum == 0:
        minimum = None
    if minimum is not None and maximum is not None and minimum != maximum:
        return "{} to {} {} per day".format(number(minimum), number(maximum), unit)
    if maximum is not None and minimum is None:
        return "up to {} {} per day".format(number(maximum), unit)
    if minimum is not None and maximum is None:
        return "at least {} {} per day".format(number(minimum), unit)
    return "exactly {} {} per day".format(number(maximum), unit)


def percent_used(value, minimum, maximum):
    if maximum is not None:
        if maximum == 0:
            return 100.0 if value > 0 else 0.0
        return value / maximum * 100
    if minimum:
        return value / minimum * 100
    return 0.0


def build_row(check, day_is_over):
    value = check["value"]
    minimum = check["minimum"]
    maximum = check["maximum"]
    unit = check["unit"].replace("/day", "").strip()
    percent = percent_used(value, minimum, maximum)

    if check["limit_crossed"]:
        state = "over"
        message = "Over the daily limit by {} {}".format(number(value - maximum), unit)
    elif maximum is not None and percent >= NEAR_LIMIT_PERCENT:
        state = "near"
        message = "Close to the daily limit"
    elif check["status"] == "below_minimum":
        state = "low" if day_is_over else "building"
        message = "Below the daily minimum" if day_is_over else "Below the daily minimum so far"
    else:
        state = "ok"
        message = "Within the daily range"

    return {
        "name": pretty_name(check["nutrient"]),
        "amount": value,
        "value": number(value),
        "unit": unit,
        "range_text": range_text(minimum, maximum, unit),
        "percent": int(min(percent, 100)),
        "state": state,
        "message": message,
    }


def limit_report(totals, profile, fallback_weight=None, day_is_over=False):
    if not profile:
        return None

    payload = {name: value for name, value in totals.items() if value is not None}
    payload["age"] = profile["age"]
    payload["gender"] = profile["gender"]
    weight = profile.get("body_weight_kg") or fallback_weight
    if weight:
        payload["body_weight_kg"] = weight

    checks, needed = evaluate_limits(payload, profile["disease"], 1)
    rows = sorted(
        (build_row(check, day_is_over) for check in checks),
        key=lambda row: (STATE_ORDER[row["state"]], row["name"]),
    )
    labels = {item["value"]: item["label"] for item in available_conditions()}
    return {
        "label": labels.get(profile["disease"], pretty_name(profile["disease"])),
        "rows": rows,
        "exceeded": [row for row in rows if row["state"] == "over"],
        "needs": [MISSING_PROFILE_TEXT.get(name, name) for name in needed],
    }
