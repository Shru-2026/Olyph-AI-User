# auth/auth.py
import os
import json
import bcrypt
from typing import Dict
from pathlib import Path

# --------------------------------------------------------------------------
# 1. Detect if running on Render (secret file available)
# --------------------------------------------------------------------------

RENDER_SECRET_FILE = Path("/etc/secrets/authorized_users.json")

if RENDER_SECRET_FILE.exists():
    # Running on Render – use secret file
    USERS_PATH = str(RENDER_SECRET_FILE)
else:
    # Running locally – use local file
    BASE_DIR = Path(__file__).resolve().parent
    USERS_PATH = str(BASE_DIR / "authorized_users.json")

# Debug print
print(f"[AUTH] Using users file: {USERS_PATH}")

# --------------------------------------------------------------------------
# Ensure existence ONLY for local file, not for Render secret
# --------------------------------------------------------------------------

def _ensure_auth_file():
    # Do NOT attempt to create Render secret file
    if str(USERS_PATH).startswith("/etc/secrets"):
        return

    path = Path(USERS_PATH)
    dirpath = path.parent

    if not dirpath.exists():
        dirpath.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        with path.open("w", encoding="utf-8") as f:
            json.dump({"users": {}}, f, indent=2)


def _load_users() -> Dict[str, str]:
    if not Path(USERS_PATH).exists():
        print("[AUTH] Warning: users file not found:", USERS_PATH)
        return {}

    with open(USERS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("users", {})


def _save_users(users: Dict[str, str]):
    # DO NOT write to Render secret file (it is read-only)
    if str(USERS_PATH).startswith("/etc/secrets"):
        raise RuntimeError(
            "Attempted to write to Render Secret File! "
            "Render secret files are read-only. Remove 'add_user' usage in production."
        )

    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, indent=2)


def add_user(username: str, password: str) -> None:
    if str(USERS_PATH).startswith("/etc/secrets"):
        raise RuntimeError("add_user cannot be used in production (secret file is read-only)")

    if not username:
        raise ValueError("username required")
    if not password:
        raise ValueError("password required")

    users = _load_users()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users[username] = hashed.decode("utf-8")
    _save_users(users)


def verify_user(username: str, password: str) -> bool:
    if not username or not password:
        return False

    users = _load_users()
    stored = users.get(username)
    if not stored:
        return False

    if stored.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))

    # Legacy plaintext support (local only)
    if password == stored:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        users[username] = hashed
        _save_users(users)
        return True

    return False


def list_users():
    return list(_load_users().keys())
