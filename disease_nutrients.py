import csv
from pathlib import Path

from database import replace_disease_nutrients

CSV_PATH = Path(__file__).resolve().parent / "datasets" / "csv" / "overall_disease_nutrition.csv"


def optional_number(value):
    text = (value or "").strip()
    if not text or text.lower() in {"none", "null", "n/a", "na", "-", "—"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def load_disease_nutrients(csv_path=CSV_PATH):
    """Read CSV rows into database-ready values without inventing limits."""
    records = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        required_columns = {
            "disease", "nutrient", "min-value", "max-value", "unit",
            "age-group", "gender", "verified",
        }
        if not required_columns.issubset(reader.fieldnames or ()):
            missing = sorted(required_columns.difference(reader.fieldnames or ()))
            raise ValueError("Disease nutrition CSV is missing columns: %s" % ", ".join(missing))

        for row in reader:
            disease = (row.get("disease") or "").strip()
            nutrient = (row.get("nutrient") or "").strip()
            if not disease or not nutrient:
                continue

            records.append((
                disease,
                nutrient,
                optional_number(row.get("min-value")),
                optional_number(row.get("max-value")),
                (row.get("unit") or "").strip() or None,
                (row.get("age-group") or "").strip() or None,
                (row.get("gender") or "").strip() or None,
                (row.get("verified") or "No").strip(),
            ))

    return records


def sync_disease_nutrients_from_csv(csv_path=CSV_PATH):
    """Replace database thresholds with the CSV source of truth."""
    records = load_disease_nutrients(csv_path)
    replace_disease_nutrients(records)
    return len(records)
