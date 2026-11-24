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

## Daily limits in the nutrition log

On **Nutrition Log** (`/health/nutrition`) each user saves a health condition, gender, age and an optional body weight (`/health/nutrition/profile`). The profile is stored per user in `nutrition_profiles` in `instance/health.db`. The condition list is built from the verified rows in `disease_nutrients`.

The day's logged foods are totalled and compared with the per-day limits for that condition using the same rules as `/nutrition/analyze` (`daily_limits.py` calls `evaluate_limits`). The page shows a bar per checked nutrient (within range, close to the limit, over the limit, or below a minimum). When adding a food pushes a nutrient over its daily limit, a warning is shown at once and stays on the page for that day.

- Only nutrients the user has logged are checked; a missing nutrient is never treated as zero.
- Minimums are shown as goals today and as "below the daily minimum" for finished days.
- If a limit is per kg of body weight, the weight entered in the profile is used, otherwise the latest weight from My Health.
- Only nutrients that the nutrition log tracks can be checked; dataset rows for others (for example magnesium or zinc) are ignored.

### `app.py` — application entry point

- Creates the Flask application.
- Configures the `statics/` directory as Flask's static-file folder.
- Configures the Flask instance directory and session-cookie settings.
- Initializes the account/disease database.
- Synchronizes disease nutrient reference data from the CSV.
- Initializes the Food Safety database tables and rules.
- Registers the authentication, health, health-check, nutrition-analysis, nutrition-dashboard, and Food Safety Blueprints.
- Applies the login requirement to protected pages and API endpoints.
- Provides the home route and shared account details to templates.

Run this file to start the local Flask application.

### `auth.py` — authentication and session management

- Implements registration, login, and logout routes.
- Validates submitted account details.
- Creates and checks user sessions.
- Provides the current logged-in user.
- Generates and validates CSRF tokens for forms.
- Uses database helper functions from `database.py`.
- Uses Werkzeug password verification helpers.

### `database.py` — account and disease-reference database

- Defines the shared instance directory and `nutricare_users.db` location.
- Opens SQLite connections and sets `row_factory = sqlite3.Row`.
- Creates and migrates the `users` and `disease_nutrients` tables.
- Creates users with hashed passwords.
- Fetches users by email or user ID.
- Verifies submitted passwords.
- Inserts, replaces, retrieves, and deletes disease-nutrient reference rows.

### `health_check.py` — BMI and calorie/health estimates

- Defines the `/bmi` and `/calories` routes.
- Reads weight, height, age, sex, activity level, and goal from the form.
- Validates numeric inputs.
- Calculates BMI and its category.
- Calculates the health estimates returned to `health_check.html`.

### `health.py` — Health Tracker routes and storage

- Defines the Health Tracker Blueprint and `health_logs` table.
- Opens the `health.db` SQLite database.
- Validates daily health-log form values.
- Adds and updates records for the logged-in user.
- Deletes records and exports health data as CSV.
- Fetches the selected 7-day or 30-day history.
- Converts fetched rows into Python dictionaries and passes them to `health.html`.
- Calls `analytics.py` to prepare dashboard statistics.

### `analytics.py` — health data analysis

- Uses Pandas to create a DataFrame from health records.
- Converts dates and sorts records chronologically.
- Calculates averages for water, sleep, and steps.
- Finds the latest recorded weight and the change between the first and last recorded weights.
- Returns summary values to the Health Tracker route.

### `nutrition_dashboard.py` — Nutrition Log routes and business logic

- Defines the Nutrition Blueprint and Nutrition Dashboard routes.
- Validates food name, food type, date, quantity, serving basis, and nutrient values.
- Scales label values to the quantity actually eaten.
- Builds the daily nutrition summary.
- Builds the seven-day nutrient-history data used by the chart.
- Loads the user's nutrition profile and daily-limit report.
- Passes food records, nutrient definitions, totals, profile information, and Food Safety preferences to `nutrition_dashboard.html`.
- Handles adding and deleting food entries and saving the nutrition profile.

### `nutrition_storage.py` — nutrition database operations

- Defines the nutrient names and their display units.
- Opens the `health.db` database.
- Creates or updates the `nutrition_entries` and `nutrition_profiles` tables.
- Stores food entries against the logged-in user's ID.
- Reads entries for a selected day or date range.
- Reads and saves the user's nutrition profile.
- Provides helper operations such as deleting an entry and retrieving the latest health weight.

### `nutrition_analysis.py` — nutrient-limit analysis API

- Defines the nutrition-analysis Blueprint.
- Normalizes disease, nutrient, and unit names.
- Validates numeric values received in an API request.
- Reads disease-nutrient reference values from `database.py`.
- Evaluates submitted nutrient amounts against applicable verified limits.
- Returns structured JSON results through the analysis endpoints.

### `daily_limits.py` — daily nutrition-limit reporting

- Builds the available health-condition list from verified reference rows.
- Compares the user's daily logged nutrient totals with the selected condition's configured limits.
- Calculates percentage usage and readable range text.
- Assigns display states such as within range, near limit, over limit, or below minimum.
- Prepares the daily-limit report shown on the Nutrition Dashboard.

### `disease_nutrients.py` — CSV reference-data loader

- Reads `datasets/csv/overall_disease_nutrition.csv`.
- Checks that the expected CSV columns are present.
- Converts optional numeric values without inventing missing limits.
- Passes parsed rows to `database.py`.
- Synchronizes the CSV reference data into the `disease_nutrients` table at application startup.

### `food_safety.py` — ingredient and food-label rule engine

- Loads `datasets/json/food_safety_rules.json`.
- Normalizes ingredient text and matches ingredient aliases.
- Extracts ingredient, contains, and may-contain sections from label text.
- Initializes and uses Food Safety tables in the nutrition database.
- Saves and retrieves each user's selected conditions, personal avoid ingredients, allergies, and relevant preferences.
- Evaluates disease-related ingredient and nutrient rules and personal preferences.
- Scales nutrient values to the quantity consumed.
- Returns an overall status, individual findings, evidence links, and review notices as JSON.
- Provides routes to save Food Safety preferences and analyze a food label.

## 5. HTML templates — `templates/`

All HTML templates use Jinja2 syntax. Flask renders them with `render_template()`.

| File | Responsibility |
|---|---|
| `index.html` | NutriCare landing page, navigation, and feature entry points |
| `login.html` | Login form, CSRF token, and authentication messages |
| `register.html` | Account creation form and validation feedback |
| `health_check.html` | BMI and health-estimate input form and result display |
| `health.html` | Health Tracker form, summary cards, charts, history, edit/delete controls, and CSV link |
| `nutrition_dashboard.html` | Food-entry form, nutrition totals, disease-limit report, Food Safety profile/check, logged-food table, and weekly chart |
| `_account_strip.html` | Reusable signed-in user display and logout form |
| `_flash_messages.html` | Reusable success and error messages |

### Jinja2 patterns used

- `{{ value }}` displays a value supplied by Python.
- `{% if condition %}` and `{% else %}` control conditional sections.
- `{% for item in items %}` repeats markup for records or nutrient cards.
- `{% include 'file.html' %}` reuses shared template components.
- `{{ records | tojson }}` serializes backend data for JavaScript use.

## 6. Frontend assets — `statics/`

| File | Responsibility |
|---|---|
| `style.css` | Landing page and Health Check page styling |
| `auth.css` | Login and registration page styling |
| `account.css` | Shared account strip, logout button, and flash-message styling |
| `health.css` | Health Tracker layout, forms, summary cards, filters, and chart layout |
| `nutrition_dashboard.css` | Nutrition forms, nutrient cards, tables, Food Safety result area, and chart layout |
| `nutrition_dashboard.js` | Browser-side nutrition-label OCR, text parsing, form auto-fill, Food Safety API request/result rendering, and weekly Chart.js interaction |

### Chart.js implementation locations

- **Health Tracker:** `health.html` loads Chart.js from a CDN and contains inline JavaScript that creates four charts: weight, water, sleep, and steps.
- **Nutrition Dashboard:** `nutrition_dashboard.html` provides the weekly data and canvas, loads Chart.js, and includes `nutrition_dashboard.js`. The JavaScript creates the weekly chart and updates it when the user selects a different nutrient.

### Tesseract.js implementation

- `nutrition_dashboard.html` loads Tesseract.js from a CDN.
- `nutrition_dashboard.js` sends selected image files to Tesseract.js in the browser.
- The JavaScript reads the recognized text, parses candidate nutrient/ingredient fields, and fills matching form inputs.
- The user must review the extracted text and values before submitting the food entry.

The test suite uses isolated temporary SQLite files. See [ARCHITECTURE.md](ARCHITECTURE.md) for routes, data flow, storage and OCR details.
