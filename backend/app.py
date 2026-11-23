from pathlib import Path

from flask import Flask, abort, jsonify, request, session, send_from_directory

import db
from config import EXAMPLE_EMAIL, HOST, PORT, SECRET_KEY

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.teardown_appcontext(db.close_db)


@app.before_request
def sign_in_example_user():
    if "userId" not in session:
        session["userId"] = db.get_user_by_email(EXAMPLE_EMAIL)["userId"]


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
    me = db.get_user(session["userId"])
    circles = db.get_circles(me["userId"])
    return jsonify({
        "userId": me["userId"],
        "name": me["firstName"] + " " + me["lastName"],
        "circles": [{"circleId": c["circleId"], "name": c["name"]} for c in circles],
    })


@app.route("/api/circles/<int:circle_id>")
def circle(circle_id):
    found = db.get_circle(circle_id, session["userId"])
    if found is None:
        abort(404)
    members = db.get_circle_members(circle_id, session["userId"])
    alerts = db.get_alerts(circle_id)
    return jsonify({
        "name": found["name"],
        "members": [
            {"userId": m["userId"], "firstName": m["firstName"], "lat": m["lat"], "lng": m["lng"]}
            for m in members
        ],
        "alerts": [
            {
                "firstName": a["firstName"],
                "name": a["name"],
                "lat": a["latitude"],
                "lng": a["longitude"],
                "time": a["time"],
            }
            for a in alerts
        ],
    })


def read_coordinates(data):
    # Returns (lat, lng), or None if they are missing or out of range.
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


@app.route("/api/location", methods=["POST"])
def location():
    coords = read_coordinates(request.get_json(silent=True) or {})
    if coords is None:
        abort(400)
    if db.get_settings(session["userId"])["pauseSharing"]:
        return jsonify({"paused": True})
    db.set_location(session["userId"], *coords)
    return jsonify({"paused": False})


@app.route("/api/alerts", methods=["POST"])
def alerts():
    data = request.get_json(silent=True) or {}
    circle_id = data.get("circleId")
    if db.get_circle(circle_id, session["userId"]) is None:
        abort(404)
    # The coordinates are optional: an SOS still goes out if the GPS fails.
    coords = read_coordinates(data) or (None, None)
    db.add_alert(circle_id, session["userId"], *coords)
    return jsonify({"sent": True})


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if data.get("setting") not in db.SETTINGS or "value" not in data:
            abort(400)
        db.set_setting(session["userId"], data["setting"], bool(data["value"]))
    return jsonify(db.get_settings(session["userId"]))


if __name__ == "__main__":
    db.init_db()
    app.run(host=HOST, port=PORT, debug=True)
