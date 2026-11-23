# NutriCare

NutriCare is a Flask-based nutrition and health tracker with daily logs, health estimates, nutrition-label OCR, and a disease-nutrient analysis API.

## Run locally

```sh
./.venv-1/bin/python app.py
```

Open `http://127.0.0.1:5000` in a browser.

## Run tests

```sh
./.venv-1/bin/python -m unittest discover -s tests -v
```

The test suite uses isolated temporary SQLite files. See [ARCHITECTURE.md](ARCHITECTURE.md) for routes, data flow, storage and OCR details.
