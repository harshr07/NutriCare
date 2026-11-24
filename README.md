# NutriCare

NutriCare is a Flask-based nutrition and health tracker with daily logs, health estimates, nutrition-label OCR, and a disease-nutrient analysis API.

## Run locally

```sh
./.venv/bin/python app.py
```

Open `http://127.0.0.1:5000` in a browser. You will be sent to the login page first; choose **Create an account** to register.

## Accounts and login

- Every page and API endpoint needs a logged-in user. Only `/login` and `/register` (and static files) are public.
- Logged-out visitors are redirected to `/login?next=<page>` and returned to that page after logging in or registering. JSON endpoints (`/nutrition/analyze`, `/nutrition-analysis`) answer `401` instead of redirecting.
- Passwords are stored as salted hashes in `instance/nutricare_users.db`. Login, register and logout forms carry a CSRF token.
- Health logs and nutrition entries are stored per user in `instance/health.db`; users only see, edit, delete and export their own records. Health logs created before login existed are kept but hidden from every account.
- Each app page shows a "Signed in as … / Log out" bar and any login messages.
- Optional settings: `NUTRICARE_SECRET_KEY` (session key; otherwise one is saved in `instance/`), `NUTRICARE_COOKIE_SECURE=1` (HTTPS-only cookies), `NUTRICARE_INSTANCE_DIR` (store the databases in another folder).

## Disease nutrient limit checks

`datasets/csv/overall_disease_nutrition.csv` is the source of truth for disease/nutrient thresholds. On startup, its rows—including the `verified`, age-group, gender and unit columns—are synced into `disease_nutrients` in `instance/nutricare_users.db`. Analysis uses only rows marked `verified=Yes`; there are no fallback limits for diseases or nutrients absent from that CSV. The input values are scaled by portion/serving before comparison. Supply `age` or `age_group` and `gender` when a CSV limit is demographic-specific. Protein limits in `g/kg body weight/day` also need `body_weight_kg`.

`POST /nutrition/analyze` returns per-nutrient status (`above_maximum`, `below_minimum`, or `within_range`), a top-level `limit_crossed` flag, and any required profile fields. This is a threshold comparison from the CSV—not a medical recommendation or a guarantee that a food is suitable.

## Run tests

```sh
./.venv/bin/python -m unittest discover -s tests -v
```

The test suite uses isolated temporary SQLite files. See [ARCHITECTURE.md](ARCHITECTURE.md) for routes, data flow, storage and OCR details.
