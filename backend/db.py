import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import g
from werkzeug.security import generate_password_hash

from config import DATABASE

SCHEMA = Path(__file__).resolve().parent / "schema.sql"

SETTINGS = (
    "pauseSharing",
    "arrivalNotifications",
    "lowBatteryNotifications",
    "completedDriveNotifications",
    "severeWeatherNotifications",
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = connect()
    db.executescript(SCHEMA.read_text())
    if db.execute("SELECT COUNT(*) FROM User").fetchone()[0] == 0:
        add_example_data(db)
    db.commit()
    db.close()


def add_example_data(db):
    password = generate_password_hash("password")
    # John is the account you sign in as. His location comes from the browser.
    people = [
        ("John", "john@example.com", None, None),
        ("Vincent", "vincent@example.com", 38.627, -90.1994),
        ("Jessica", "jessica@example.com", 38.5834, -90.4068),
        ("Victoria", "victoria@example.com", 38.6489, -90.3301),
    ]
    ids = {}
    for first, email, lat, lng in people:
        cur = db.execute(
            "INSERT INTO User (firstName, lastName, email, phoneNumber, passwordHash,"
            " lastLatitude, lastLongitude, lastUpdated) VALUES (?, 'Demo', ?, '', ?, ?, ?, ?)",
            (first, email, password, lat, lng, now() if lat is not None else None),
        )
        ids[first] = cur.lastrowid

    circles = {
        "Family": ["John", "Vincent", "Jessica"],
        "Friends": ["John", "Victoria"],
    }
    for name, members in circles.items():
        circle_id = db.execute(
            "INSERT INTO Circle (name, ownerId) VALUES (?, ?)", (name, ids["John"])
        ).lastrowid
        for member in members:
            db.execute(
                "INSERT INTO CircleMembers (circleId, userId) VALUES (?, ?)",
                (circle_id, ids[member]),
            )


def get_user(user_id):
    return get_db().execute("SELECT * FROM User WHERE userId = ?", (user_id,)).fetchone()


def get_user_by_email(email):
    return get_db().execute("SELECT * FROM User WHERE email = ?", (email,)).fetchone()


def get_circles(user_id):
    return get_db().execute(
        "SELECT Circle.circleId, Circle.name FROM Circle"
        " JOIN CircleMembers USING (circleId)"
        " WHERE CircleMembers.userId = ? ORDER BY Circle.name",
        (user_id,),
    ).fetchall()


def get_circle(circle_id, user_id):
    # Only returns the circle if this user is a member of it.
    return get_db().execute(
        "SELECT Circle.* FROM Circle JOIN CircleMembers USING (circleId)"
        " WHERE Circle.circleId = ? AND CircleMembers.userId = ?",
        (circle_id, user_id),
    ).fetchone()


def get_circle_members(circle_id, viewer_id):
    # Someone who paused sharing shows no location to the others, only to themselves.
    return get_db().execute(
        "SELECT userId, firstName,"
        " CASE WHEN pauseSharing = 1 AND userId != ?1 THEN NULL ELSE lastLatitude END AS lat,"
        " CASE WHEN pauseSharing = 1 AND userId != ?1 THEN NULL ELSE lastLongitude END AS lng"
        " FROM User JOIN CircleMembers USING (userId)"
        " WHERE CircleMembers.circleId = ?2 ORDER BY firstName",
        (viewer_id, circle_id),
    ).fetchall()


def get_settings(user_id):
    row = get_db().execute(
        "SELECT " + ", ".join(SETTINGS) + " FROM User WHERE userId = ?", (user_id,)
    ).fetchone()
    return {key: bool(row[key]) for key in SETTINGS}


def set_setting(user_id, key, value):
    if key not in SETTINGS:
        raise ValueError("Unknown setting: " + key)
    db = get_db()
    db.execute("UPDATE User SET " + key + " = ? WHERE userId = ?", (int(value), user_id))
    db.commit()


def set_location(user_id, lat, lng):
    db = get_db()
    db.execute(
        "UPDATE User SET lastLatitude = ?, lastLongitude = ?, lastUpdated = ? WHERE userId = ?",
        (lat, lng, now(), user_id),
    )
    db.commit()


def add_alert(circle_id, user_id, lat, lng):
    db = get_db()
    db.execute(
        "INSERT INTO Alerts (circleId, userId, name, latitude, longitude, time)"
        " VALUES (?, ?, 'SOS', ?, ?, ?)",
        (circle_id, user_id, lat, lng, now()),
    )
    db.commit()


def get_alerts(circle_id):
    return get_db().execute(
        "SELECT User.firstName, Alerts.name, Alerts.latitude, Alerts.longitude, Alerts.time"
        " FROM Alerts JOIN User USING (userId)"
        " WHERE Alerts.circleId = ? ORDER BY Alerts.time DESC LIMIT 10",
        (circle_id,),
    ).fetchall()
