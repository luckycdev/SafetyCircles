# Safety Circles

### Project Overview

Safety Circles is a web-based personal safety application that helps users share their location with trusted contacts and send emergency alerts.

---

### Instructions to run the app
1. Install Python
2. Run `pip install -r backend/requirements.txt`
3. Modify backend/config.py if you need to
4. Run `py backend/app.py`
5. View the app at `127.0.0.1:5000` (5000 may be different if you changed config.py)

The first run creates `backend/data/safetycircles.db` with an example account (john@example.com, password `password`). There is no login page yet, so you are signed in as that account automatically. John's location comes from your browser, so allow location access. Delete the .db file to reset it.

### Technology Stack

Backend: Python

Backend Framework: Flask

Frontend: HTML, CSS and JavaScript

Location Services: Browser Geolocation API

Version Control: GitHub

### Main Features

User registration and login.

Create and manage trusted safety circles.

Share real-time location with trusted contacts.

Send emergency SOS alerts.

Display user location on an interactive map.

Manage location-sharing and notification settings.

### Development Goals

Set up the Python Flask backend.

Build the initial frontend interface.

Integrate an interactive map.

Implement location-sharing functionality.

Develop emergency alert features.

### Project Status

Initial development and project setup.