# What happens when someone's phone reports a new location:
# arrival/departure alerts, low battery alerts, drive tracking and weather alerts.
import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

import db as database

DRIVE_MPH = 10        # at or above this speed someone counts as driving
STOPPED_MPH = 3       # below this speed someone counts as stopped
STOP_SECONDS = 120    # stopped for this long ends a drive
GAP_SECONDS = 180     # no updates for this long also ends a drive
MIN_DRIVE_MILES = 0.1
LOW_BATTERY = 20
WEATHER_EVERY = 600   # seconds between weather checks for one person


def meters_between(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def miles_between(lat1, lng1, lat2, lng2):
    return meters_between(lat1, lng1, lat2, lng2) / 1609.344


def seconds_since(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()


def notify(db, user_ids, kind, message, key=None):
    for user_id in user_ids:
        db.execute(
            "INSERT OR IGNORE INTO Notifications (userId, type, message, time, uniqueKey)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, message, database.now(), key),
        )


def only_if_on(db, user_ids, setting):
    # Keeps the people who have this notification turned on.
    if setting not in database.SETTINGS or not user_ids:
        return []
    marks = ",".join("?" * len(user_ids))
    rows = db.execute(
        "SELECT userId FROM User WHERE " + setting + " = 1 AND userId IN (" + marks + ")",
        list(user_ids),
    ).fetchall()
    return [r["userId"] for r in rows]


def circle_member_ids(db, circle_id, except_id):
    rows = db.execute(
        "SELECT userId FROM CircleMembers WHERE circleId = ? AND userId != ?",
        (circle_id, except_id),
    ).fetchall()
    return [r["userId"] for r in rows]


def circle_mate_ids(db, user_id):
    rows = db.execute(
        "SELECT DISTINCT b.userId FROM CircleMembers a JOIN CircleMembers b"
        " ON a.circleId = b.circleId WHERE a.userId = ? AND b.userId != ?",
        (user_id, user_id),
    ).fetchall()
    return [r["userId"] for r in rows]


def record_location(db, user_id, lat, lng, speed=None, battery=None, when=None):
    """Saves a new location (speed in mph, battery in percent) and reacts to it."""
    when = when or datetime.now(timezone.utc)
    user = db.execute("SELECT * FROM User WHERE userId = ?", (user_id,)).fetchone()
    had_location = user["lastLatitude"] is not None

    # Some devices report no speed, so work it out from the last position.
    if speed is None and had_location and user["lastUpdated"]:
        seconds = (when - datetime.fromisoformat(user["lastUpdated"])).total_seconds()
        if 1 <= seconds <= 120:
            miles = miles_between(user["lastLatitude"], user["lastLongitude"], lat, lng)
            speed = miles / seconds * 3600

    db.execute(
        "UPDATE User SET lastLatitude = ?, lastLongitude = ?, lastUpdated = ?, lastSpeed = ?,"
        " batteryLevel = COALESCE(?, batteryLevel) WHERE userId = ?",
        (lat, lng, when.isoformat(timespec="seconds"), speed, battery, user_id),
    )

    if had_location:
        check_places(db, user, lat, lng)
    check_battery(db, user, battery)
    update_route(db, user, lat, lng, speed, when)
    db.commit()


def check_places(db, user, lat, lng):
    places = db.execute(
        "SELECT Places.* FROM Places JOIN CircleMembers USING (circleId)"
        " WHERE CircleMembers.userId = ?",
        (user["userId"],),
    ).fetchall()
    for place in places:
        was_in = meters_between(
            user["lastLatitude"], user["lastLongitude"], place["latitude"], place["longitude"]
        ) <= place["radius"]
        is_in = meters_between(lat, lng, place["latitude"], place["longitude"]) <= place["radius"]
        if was_in == is_in:
            continue
        verb = "arrived at" if is_in else "left"
        others = circle_member_ids(db, place["circleId"], user["userId"])
        notify(
            db,
            only_if_on(db, others, "arrivalNotifications"),
            "place",
            user["firstName"] + " " + verb + " " + place["name"],
        )


def check_battery(db, user, battery):
    old = user["batteryLevel"]
    if battery is None or old is None or not (old > LOW_BATTERY >= battery):
        return
    ids = only_if_on(db, circle_mate_ids(db, user["userId"]), "lowBatteryNotifications")
    notify(db, ids, "battery", user["firstName"] + "'s battery is at " + str(battery) + "%")


def update_route(db, user, lat, lng, speed, when):
    user_id = user["userId"]
    stamp = when.isoformat(timespec="seconds")
    route = db.execute(
        "SELECT * FROM Routes WHERE userId = ? AND finished = 0", (user_id,)
    ).fetchone()

    # Updates stopped coming, so that drive is over.
    if route is not None:
        gap = (when - datetime.fromisoformat(route["endTime"])).total_seconds()
        if gap > GAP_SECONDS:
            finish_route(db, route["routeId"])
            route = None

    if route is None:
        if speed is not None and speed >= DRIVE_MPH:
            db.execute(
                "INSERT INTO Routes (userId, startingLat, startingLong, endLat, endLong,"
                " secondsTaken, distanceMiles, topSpeed, startTime, endTime, lastMoving)"
                " VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)",
                (user_id, lat, lng, lat, lng, speed, stamp, stamp, stamp),
            )
        return

    miles = route["distanceMiles"] + miles_between(route["endLat"], route["endLong"], lat, lng)
    moving = speed is not None and speed >= STOPPED_MPH
    last_moving = stamp if moving else route["lastMoving"]
    seconds = int((when - datetime.fromisoformat(route["startTime"])).total_seconds())
    db.execute(
        "UPDATE Routes SET endLat = ?, endLong = ?, endTime = ?, secondsTaken = ?,"
        " distanceMiles = ?, topSpeed = ?, lastMoving = ? WHERE routeId = ?",
        (lat, lng, stamp, seconds, miles, max(route["topSpeed"], speed or 0),
         last_moving, route["routeId"]),
    )

    stopped_for = (when - datetime.fromisoformat(last_moving)).total_seconds()
    if stopped_for >= STOP_SECONDS:
        finish_route(db, route["routeId"])


def finish_route(db, route_id):
    route = db.execute(
        "SELECT Routes.*, User.firstName FROM Routes JOIN User USING (userId)"
        " WHERE routeId = ?",
        (route_id,),
    ).fetchone()
    if route["distanceMiles"] < MIN_DRIVE_MILES:
        db.execute("DELETE FROM Routes WHERE routeId = ?", (route_id,))
        return
    db.execute("UPDATE Routes SET finished = 1 WHERE routeId = ?", (route_id,))
    minutes = max(1, round(route["secondsTaken"] / 60))
    ids = only_if_on(db, circle_mate_ids(db, route["userId"]), "completedDriveNotifications")
    notify(
        db,
        ids,
        "drive",
        "%s finished a drive (%.1f mi, %d min)" % (route["firstName"], route["distanceMiles"], minutes),
    )


def finish_stale_routes(db):
    # A phone that went quiet never sends the update that ends its drive.
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=GAP_SECONDS)
    old = db.execute(
        "SELECT routeId FROM Routes WHERE finished = 0 AND endTime < ?",
        (cutoff.isoformat(timespec="seconds"),),
    ).fetchall()
    for row in old:
        finish_route(db, row["routeId"])
    db.commit()


last_weather_check = {}


def check_weather_later(user_id, lat, lng):
    # Asks the National Weather Service in the background, at most every 10 minutes.
    if time.time() - last_weather_check.get(user_id, 0) < WEATHER_EVERY:
        return
    last_weather_check[user_id] = time.time()
    threading.Thread(target=check_weather, args=(user_id, lat, lng), daemon=True).start()


def check_weather(user_id, lat, lng):
    request = Request(
        "https://api.weather.gov/alerts/active?point=%.4f,%.4f" % (lat, lng),
        headers={"User-Agent": "SafetyCircles school project", "Accept": "application/geo+json"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            alerts = json.load(response)["features"]
    except Exception:
        return

    db = database.connect()
    try:
        for alert in alerts:
            info = alert["properties"]
            if info.get("severity") not in ("Severe", "Extreme"):
                continue
            message = info["event"] + ": " + (info.get("headline") or "")
            # The alert id is the key, so the same alert is only sent once.
            notify(db, [user_id], "weather", message[:250], key=alert["id"])
        db.commit()
    finally:
        db.close()
