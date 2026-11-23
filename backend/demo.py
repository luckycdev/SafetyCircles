# Buttons in Settings that move the example people around, so every
# notification can be tried without a second phone. Safe to delete later.
from datetime import datetime, timedelta, timezone

import tracking


def person(db, first_name):
    return db.execute("SELECT * FROM User WHERE firstName = ?", (first_name,)).fetchone()


def run(db, action):
    if action in ("jessica-arrive", "jessica-leave"):
        jessica = person(db, "Jessica")
        place = db.execute(
            "SELECT Places.* FROM Places JOIN CircleMembers USING (circleId)"
            " WHERE CircleMembers.userId = ? LIMIT 1",
            (jessica["userId"],),
        ).fetchone()
        if place is None:
            raise ValueError("Create a place in the Family circle first.")
        if action == "jessica-arrive":
            tracking.record_location(db, jessica["userId"], place["latitude"], place["longitude"], 0)
            return "Jessica arrived at " + place["name"] + "."
        tracking.record_location(db, jessica["userId"], place["latitude"] + 0.05, place["longitude"], 0)
        return "Jessica moved away from " + place["name"] + "."

    if action == "vincent-drive":
        vincent = person(db, "Vincent")
        lat, lng = vincent["lastLatitude"], vincent["lastLongitude"]
        step = -0.008 if lat > 38.68 else 0.008
        start = datetime.now(timezone.utc) - timedelta(minutes=12)
        for minute in range(6):
            lat += step
            tracking.record_location(db, vincent["userId"], lat, lng, 33, None, start + timedelta(minutes=minute))
        # Stopped for two minutes, which ends the drive
        tracking.record_location(db, vincent["userId"], lat, lng, 0, None, start + timedelta(minutes=8))
        return "Vincent drove about 3 miles and stopped."

    if action == "victoria-battery":
        victoria = person(db, "Victoria")
        level = 80 if victoria["batteryLevel"] <= tracking.LOW_BATTERY else 15
        tracking.record_location(
            db, victoria["userId"], victoria["lastLatitude"], victoria["lastLongitude"], 0, level
        )
        return "Victoria's battery is now " + str(level) + "%."

    raise ValueError("Unknown demo action.")
