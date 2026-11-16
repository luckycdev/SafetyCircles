import csv
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

from config import HOST, PORT

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

app = Flask(__name__)


def load_people():
    with open(BACKEND_DIR / "data" / "demo_data.csv", newline="", encoding="utf-8") as f:
        return [
            {
                "name": row["name"].strip(),
                "city": row["city"].strip(),
                "lat": float(row["lat"]),
                "lng": float(row["lng"]),
                "is_user": row["is_user"].strip().lower() == "true",
            }
            for row in csv.DictReader(f)
        ]


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/index.css")
def css():
    return send_from_directory(FRONTEND_DIR, "index.css")


@app.route("/index.js")
def js():
    return send_from_directory(FRONTEND_DIR, "index.js")


@app.route("/<name>.html")
def panel(name):
    if name not in ("places", "settings"):
        abort(404)
    return send_from_directory(FRONTEND_DIR, name + ".html")


@app.route("/api/user")
def user():
    people = load_people()
    me = next((p for p in people if p["is_user"]), people[0])
    return jsonify({"name": me["name"], "city": me["city"], "circle": people})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)
