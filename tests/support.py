
import atexit
import os
import re
import shutil
import tempfile

_TEMP_DIR = tempfile.mkdtemp(prefix="nutricare-tests-")
os.environ.setdefault("NUTRICARE_INSTANCE_DIR", _TEMP_DIR)
atexit.register(shutil.rmtree, _TEMP_DIR, ignore_errors=True)

TOKEN_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


def csrf_token(client, path):
    match = TOKEN_PATTERN.search(client.get(path).data)
    if not match:
        raise AssertionError("{} did not provide a CSRF token".format(path))
    return match.group(1).decode()


def register(client, email, password="safe-password-123", full_name="NutriCare Test"):
    return client.post("/register", data={
        "csrf_token": csrf_token(client, "/register"),
        "full_name": full_name,
        "email": email,
        "password": password,
        "confirm_password": password,
    })


def login(client, email, password="safe-password-123", next_url=None):
    path = "/login" if not next_url else "/login?next=" + next_url
    return client.post(path, data={
        "csrf_token": csrf_token(client, path),
        "email": email,
        "password": password,
    })


def logout(client):
    # The logout form (and its token) is part of the account strip on every page.
    return client.post("/logout", data={"csrf_token": csrf_token(client, "/")})
