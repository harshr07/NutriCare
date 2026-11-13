import pandas as pd


def analyze_health(records):
    """Summarize records. Missing measurements stay missing, not zero."""
    if not records:
        return {"count": 0, "weight": None, "weight_change": None,
                "water": None, "sleep": None, "steps": None, "logged_days": 0}

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    def avg(column):
        value = df[column].mean()
        return None if pd.isna(value) else round(float(value), 2)

    weights = df["weight"].dropna()
    change = round(float(weights.iloc[-1] - weights.iloc[0]), 2) if len(weights) > 1 else None
    return {
        "count": len(df), "weight": float(weights.iloc[-1]) if len(weights) else None,
        "weight_change": change, "water": avg("water"),
        "sleep": avg("sleep"), "steps": avg("steps"),
        "logged_days": df["date"].dt.date.nunique(),
    }
