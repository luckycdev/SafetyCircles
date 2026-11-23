from pathlib import Path

HOST = "0.0.0.0"
PORT = 5000

DATABASE = Path(__file__).resolve().parent / "data" / "safetycircles.db"
SECRET_KEY = "change-this-before-deploying"

# There is no login page yet, so everyone is signed in as this account.
EXAMPLE_EMAIL = "john@example.com"
