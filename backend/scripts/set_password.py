"""Create/refresh backend/.env secrets and the owner password.

  python scripts/set_password.py            -> asks for a password (hidden input)
  python scripts/set_password.py --generate -> random password written to backend/.owner-password.txt
The password itself is never stored in .env - only its PBKDF2 hash."""
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.security import hash_password  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
env_path = BACKEND / ".env"
lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
env = dict(l.split("=", 1) for l in lines if "=" in l and not l.startswith("#"))

if "--generate" in sys.argv:
    pw = secrets.token_urlsafe(14)
    (BACKEND / ".owner-password.txt").write_text(f"username: owner\npassword: {pw}\n", encoding="utf-8")
    print("Random owner password written to backend/.owner-password.txt (git-ignored). Change it later.")
else:
    pw = getpass.getpass("New owner password (min 10 chars): ")
    if len(pw) < 10 or pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords do not match or are too short.")

env.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
env["OWNER_USERNAME"] = env.get("OWNER_USERNAME", "owner")
env["OWNER_PASSWORD_HASH"] = hash_password(pw)
env_path.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n", encoding="utf-8")
print("backend/.env updated (SECRET_KEY set, OWNER_PASSWORD_HASH set).")
