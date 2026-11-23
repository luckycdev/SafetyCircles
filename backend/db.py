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
        ("John", "john@example.com", None, None, None),
        ("Vincent", "vincent@example.com", 38.627, -90.1994, 85),
        ("Jessica", "jessica@example.com", 38.5834, -90.4068, 70),
        ("Victoria", "victoria@example.com", 38.6489, -90.3301, 55),
    ]
    ids = {}
    for first, email, lat, lng, battery in people:
        cur = db.execute(
            "INSERT INTO User (firstName, lastName, email, phoneNumber, passwordHash,"
            " lastLatitude, lastLongitude, lastUpdated, batteryLevel)"
            " VALUES (?, 'Demo', ?, '', ?, ?, ?, ?, ?)",
            (first, email, password, lat, lng, now() if lat is not None else None, battery),
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
    # Someone who paused sharing shows nothing to the others, only to themselves.
    hidden = "(pauseSharing = 1 AND userId != ?1)"
    return get_db().execute(
        "SELECT userId, firstName,"
        " CASE WHEN " + hidden + " THEN NULL ELSE lastLatitude END AS lat,"
        " CASE WHEN " + hidden + " THEN NULL ELSE lastLongitude END AS lng,"
        " CASE WHEN " + hidden + " THEN NULL ELSE lastUpdated END AS updated,"
        " CASE WHEN " + hidden + " THEN NULL ELSE batteryLevel END AS battery,"
        " CASE WHEN " + hidden + " THEN NULL ELSE lastSpeed END AS speed"
        " FROM User JOIN CircleMembers USING (userId)"
        " WHERE CircleMembers.circleId = ?2 ORDER BY firstName",
        (viewer_id, circle_id),
    ).fetchall()


def shares_circle(user_a, user_b):
    row = get_db().execute(
        "SELECT 1 FROM CircleMembers a JOIN CircleMembers b ON a.circleId = b.circleId"
        " WHERE a.userId = ? AND b.userId = ? LIMIT 1",
        (user_a, user_b),
    ).fetchone()
    return row is not None


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


def update_account(user_id, first_name, last_name, email, phone):
    db = get_db()
    db.execute(
        "UPDATE User SET firstName = ?, lastName = ?, email = ?, phoneNumber = ?"
        " WHERE userId = ?",
        (first_name, last_name, email, phone, user_id),
    )
    db.commit()


def set_password(user_id, new_password):
    db = get_db()
    db.execute(
        "UPDATE User SET passwordHash = ? WHERE userId = ?",
        (generate_password_hash(new_password), user_id),
    )
    db.commit()


def get_user_places(user_id):
    # Every place in every circle this user belongs to.
    return get_db().execute(
        "SELECT Places.*, Circle.name AS circleName, Circle.ownerId AS ownerId"
        " FROM Places JOIN Circle USING (circleId)"
        " JOIN CircleMembers USING (circleId)"
        " WHERE CircleMembers.userId = ? ORDER BY Circle.name, Places.name",
        (user_id,),
    ).fetchall()


def get_circle_places(circle_id):
    return get_db().execute(
        "SELECT * FROM Places WHERE circleId = ? ORDER BY name", (circle_id,)
    ).fetchall()


def add_place(user_id, circle_id, name, address, lat, lng, radius):
    db = get_db()
    cur = db.execute(
        "INSERT INTO Places (userId, circleId, name, address, latitude, longitude, radius)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, circle_id, name, address, lat, lng, radius),
    )
    db.commit()
    return cur.lastrowid


def delete_place(place_id, user_id):
    # Only the person who made the place, or the circle's owner, can delete it.
    db = get_db()
    cur = db.execute(
        "DELETE FROM Places WHERE placeId = ? AND (userId = ? OR circleId IN"
        " (SELECT circleId FROM Circle WHERE ownerId = ?))",
        (place_id, user_id, user_id),
    )
    db.commit()
    return cur.rowcount > 0


def add_alert(circle_id, user_id, lat, lng):
    db = get_db()
    db.execute(
        "INSERT INTO Alerts (circleId, userId, name, latitude, longitude, time)"
        " VALUES (?, ?, 'SOS', ?, ?, ?)",
        (circle_id, user_id, lat, lng, now()),
    )
    db.commit()


def resolve_alerts(user_id):
    # Ends this person's active SOS alerts and returns the circles they were sent to.
    db = get_db()
    circles = [
        r["circleId"]
        for r in db.execute(
            "SELECT DISTINCT circleId FROM Alerts WHERE userId = ? AND resolved = 0", (user_id,)
        )
    ]
    db.execute("UPDATE Alerts SET resolved = 1 WHERE userId = ? AND resolved = 0", (user_id,))
    db.commit()
    return circles


def get_alerts(circle_id):
    return get_db().execute(
        "SELECT User.firstName, Alerts.name, Alerts.latitude, Alerts.longitude, Alerts.time"
        " FROM Alerts JOIN User USING (userId)"
        " WHERE Alerts.circleId = ? AND Alerts.resolved = 0"
        " ORDER BY Alerts.time DESC LIMIT 10",
        (circle_id,),
    ).fetchall()


def get_notifications(user_id, after=None):
    if after is None:
        return get_db().execute(
            "SELECT * FROM Notifications WHERE userId = ? ORDER BY notificationId DESC LIMIT 30",
            (user_id,),
        ).fetchall()
    return get_db().execute(
        "SELECT * FROM Notifications WHERE userId = ? AND notificationId > ?"
        " ORDER BY notificationId",
        (user_id, after),
    ).fetchall()


def get_last_notification_id(user_id):
    row = get_db().execute(
        "SELECT MAX(notificationId) AS last FROM Notifications WHERE userId = ?", (user_id,)
    ).fetchone()
    return row["last"] or 0


def get_routes(user_id):
    return get_db().execute(
        "SELECT * FROM Routes WHERE userId = ? ORDER BY startTime DESC LIMIT 20", (user_id,)
    ).fetchall()
