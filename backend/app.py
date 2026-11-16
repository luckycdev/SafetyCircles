from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from config import HOST, PORT

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/index.css")
def index_css():
    return send_from_directory(FRONTEND_DIR, "index.css")


@app.route("/index.js")
def index_js():
    return send_from_directory(FRONTEND_DIR, "index.js")


@app.route("/api/health")
def health_check():
    return jsonify({
        "status": "ok",
        "message": "Safety Circles backend is running."
    })


@app.route("/api/user")
def user_profile():
    return jsonify({
        "name": "Demo User",
        "safetyCircle": ["Vincent", "Jessica", "Victoria"]
    })


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)