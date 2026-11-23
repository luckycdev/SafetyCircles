from pathlib import Path

from flask import Flask, abort, jsonify, request, session, send_from_directory
from werkzeug.security import check_password_hash

import db
import demo
import tracking
from config import EXAMPLE_USER_ID, HOST, PORT, SECRET_KEY

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
PANELS = ("places", "settings", "account", "notifications", "routes")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.teardown_appcontext(db.close_db)


@app.before_request
def sign_in_example_user():
    if "userId" not in session:
        session["userId"] = EXAMPLE_USER_ID


def fail(message, code=400):
    return jsonify({"error": message}), code


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/index.css")
def css():
    return send_from_directory(FRONTEND_DIR, "index.css")


@app.route("/<name>.js")
def script(name):
    if name not in ("index", "panels"):
        abort(404)
    return send_from_directory(FRONTEND_DIR, name + ".js")


@app.route("/<name>.html")
def panel(name):
    if name not in PANELS:
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
    tracking.finish_stale_routes(db.get_db())
    places = db.get_circle_places(circle_id)

    members = []
    for m in db.get_circle_members(circle_id, session["userId"]):
        place = None
        driving = None
        if m["lat"] is not None:
            for p in places:
                if tracking.meters_between(m["lat"], m["lng"], p["latitude"], p["longitude"]) <= p["radius"]:
                    place = p["name"]
                    break
            recent = tracking.seconds_since(m["updated"]) < 120
            if recent and m["speed"] is not None and m["speed"] >= tracking.DRIVE_MPH:
                driving = round(m["speed"])
        members.append({
            "userId": m["userId"],
            "firstName": m["firstName"],
            "lat": m["lat"],
            "lng": m["lng"],
            "updated": m["updated"],
            "battery": m["battery"],
            "speed": driving,
            "place": place,
        })

    return jsonify({
        "name": found["name"],
        "members": members,
        "places": [
            {"placeId": p["placeId"], "name": p["name"], "lat": p["latitude"],
             "lng": p["longitude"], "radius": p["radius"]}
            for p in places
        ],
        "alerts": [
            {"firstName": a["firstName"], "name": a["name"], "lat": a["latitude"],
             "lng": a["longitude"], "time": a["time"]}
            for a in db.get_alerts(circle_id)
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


def read_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@app.route("/api/location", methods=["POST"])
def location():
    data = request.get_json(silent=True) or {}
    coords = read_coordinates(data)
    if coords is None:
        return fail("Bad coordinates.")
    me = session["userId"]
    if db.get_settings(me)["pauseSharing"]:
        return jsonify({"paused": True})

    speed = read_number(data.get("speed"))
    battery = read_number(data.get("battery"))
    if battery is not None:
        battery = max(0, min(100, round(battery)))
    tracking.record_location(db.get_db(), me, coords[0], coords[1], speed, battery)

    if db.get_settings(me)["severeWeatherNotifications"]:
        tracking.check_weather_later(me, coords[0], coords[1])
    return jsonify({"paused": False})


@app.route("/api/alerts", methods=["POST"])
def alerts():
    data = request.get_json(silent=True) or {}
    circle_id = data.get("circleId")
    if db.get_circle(circle_id, session["userId"]) is None:
        abort(404)
    me = db.get_user(session["userId"])
    # The coordinates are optional: an SOS still goes out if the GPS fails.
    coords = read_coordinates(data) or (None, None)
    db.add_alert(circle_id, me["userId"], *coords)

    conn = db.get_db()
    others = tracking.circle_member_ids(conn, circle_id, me["userId"])
    tracking.notify(conn, others, "sos", me["firstName"] + " sent an SOS alert")
    conn.commit()
    return jsonify({"sent": True})


@app.route("/api/alerts/resolve", methods=["POST"])
def resolve_alerts():
    me = db.get_user(session["userId"])
    conn = db.get_db()
    for circle_id in db.resolve_alerts(me["userId"]):
        others = tracking.circle_member_ids(conn, circle_id, me["userId"])
        tracking.notify(conn, others, "sos", me["firstName"] + " ended their SOS alert")
    conn.commit()
    return jsonify({"resolved": True})


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if data.get("setting") not in db.SETTINGS or "value" not in data:
            return fail("Unknown setting.")
        db.set_setting(session["userId"], data["setting"], bool(data["value"]))
    return jsonify(db.get_settings(session["userId"]))


@app.route("/api/places", methods=["GET", "POST"])
def places():
    me = session["userId"]
    if request.method == "GET":
        return jsonify([
            {
                "placeId": p["placeId"],
                "name": p["name"],
                "address": p["address"],
                "radius": p["radius"],
                "circleId": p["circleId"],
                "circleName": p["circleName"],
                "canDelete": me in (p["userId"], p["ownerId"]),
            }
            for p in db.get_user_places(me)
        ])

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    coords = read_coordinates(data)
    radius = read_number(data.get("radius"))
    if not name or len(name) > 50:
        return fail("Give the place a name (50 characters or fewer).")
    if coords is None:
        return fail("Choose a spot on the map first.")
    if radius is None or not 25 <= radius <= 5000:
        return fail("The radius must be between 25 and 5000 meters.")
    if db.get_circle(data.get("circleId"), me) is None:
        return fail("Pick one of your circles.")
    place_id = db.add_place(
        me, data["circleId"], name, str(data.get("address") or "").strip()[:255],
        coords[0], coords[1], radius,
    )
    return jsonify({"placeId": place_id})


@app.route("/api/places/<int:place_id>", methods=["DELETE"])
def delete_place(place_id):
    if not db.delete_place(place_id, session["userId"]):
        abort(404)
    return jsonify({"deleted": True})


@app.route("/api/account", methods=["GET", "POST"])
def account():
    me = db.get_user(session["userId"])
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        first = str(data.get("firstName") or "").strip()
        last = str(data.get("lastName") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        phone = str(data.get("phoneNumber") or "").strip()
        if not first or not last:
            return fail("Enter a first and last name.")
        if "@" not in email or "." not in email.split("@")[-1]:
            return fail("Enter a valid email address.")
        other = db.get_user_by_email(email)
        if other is not None and other["userId"] != me["userId"]:
            return fail("That email is already used by another account.", 409)
        db.update_account(me["userId"], first, last, email, phone)
        me = db.get_user(me["userId"])
    return jsonify({
        "firstName": me["firstName"],
        "lastName": me["lastName"],
        "email": me["email"],
        "phoneNumber": me["phoneNumber"],
        "name": me["firstName"] + " " + me["lastName"],
    })


@app.route("/api/password", methods=["POST"])
def password():
    me = db.get_user(session["userId"])
    data = request.get_json(silent=True) or {}
    if not check_password_hash(me["passwordHash"], str(data.get("current") or "")):
        return fail("Your current password is wrong.", 403)
    new_password = str(data.get("new") or "")
    if len(new_password) < 8:
        return fail("The new password needs at least 8 characters.")
    db.set_password(me["userId"], new_password)
    return jsonify({"changed": True})


@app.route("/api/notifications")
def notifications():
    tracking.finish_stale_routes(db.get_db())
    me = session["userId"]
    items = db.get_notifications(me, request.args.get("after", type=int))
    return jsonify({
        "items": [
            {"id": n["notificationId"], "type": n["type"], "message": n["message"], "time": n["time"]}
            for n in items
        ],
        "lastId": db.get_last_notification_id(me),
    })


@app.route("/api/users/<int:user_id>/routes")
def routes(user_id):
    me = session["userId"]
    if user_id != me and not db.shares_circle(me, user_id):
        abort(404)
    tracking.finish_stale_routes(db.get_db())
    person = db.get_user(user_id)
    return jsonify({
        "name": person["firstName"],
        "routes": [
            {
                "routeId": r["routeId"],
                "start": {"lat": r["startingLat"], "lng": r["startingLong"]},
                "end": {"lat": r["endLat"], "lng": r["endLong"]},
                "startTime": r["startTime"],
                "seconds": r["secondsTaken"],
                "miles": r["distanceMiles"],
                "topSpeed": r["topSpeed"],
                "active": not r["finished"],
            }
            for r in db.get_routes(user_id)
        ],
    })


@app.route("/api/demo", methods=["POST"])
def demo_action():
    data = request.get_json(silent=True) or {}
    try:
        message = demo.run(db.get_db(), str(data.get("action")))
    except ValueError as error:
        return fail(str(error))
    return jsonify({"message": message})


if __name__ == "__main__":
    db.init_db()
    app.run(host=HOST, port=PORT, debug=True)
