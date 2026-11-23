const circleSelect = document.getElementById('circle-select');


// Small helpers
async function getJSON(url) {
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Request failed: ' + url);
  }

  return res.json();
}

// Sends JSON and returns { ok, data } so forms can show the error message
async function send(url, data, method = 'POST') {
  const res = await fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data)
  });

  let body = {};

  try {
    body = await res.json();
  } catch {
    // The response had no JSON, so there is no error message to show
  }

  return { ok: res.ok, data: body };
}

function escapeHTML(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function timeAgo(iso) {
  if (!iso) return 'never';

  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;

  if (seconds < 45) return 'just now';
  if (seconds < 3600) return Math.round(seconds / 60) + ' min ago';
  if (seconds < 86400) return Math.round(seconds / 3600) + ' h ago';
  return Math.round(seconds / 86400) + ' days ago';
}

function getPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(null);
      return;
    }

    navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), {
      timeout: 10000
    });
  });
}

async function getBatteryLevel() {
  if (!navigator.getBattery) return null;

  try {
    const battery = await navigator.getBattery();
    return Math.round(battery.level * 100);
  } catch {
    return null;
  }
}


// Initialize Leaflet map
const map = L.map('map', { zoomControl: false }).setView([38.627, -90.1994], 11);

// The zoom buttons would sit under the circle selector at the top left
L.control.zoom({ position: 'bottomleft' }).addTo(map);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const placeLayer = L.layerGroup().addTo(map);
const markers = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);

const memberNames = {};
let currentUserId = null;
let openPopupUser = null;
let redrawing = false;


// Create map markers
function pin(name, color) {
  return L.divIcon({
    className: '',
    html: `<div class="pin"><span>${escapeHTML(name)}</span><i style="background:${color}"></i></div>`,
    iconSize: [120, 40],
    iconAnchor: [60, 38],
    popupAnchor: [0, -40]
  });
}

// What shows when you click someone's pin
function popupHTML(m) {
  const lines = [
    `<strong>${escapeHTML(m.firstName)}</strong>`,
    'Updated ' + timeAgo(m.updated)
  ];

  if (m.battery !== null) lines.push('Battery: ' + m.battery + '%');
  if (m.speed !== null) lines.push('Driving: ' + m.speed + ' mph');
  if (m.place) lines.push('At ' + escapeHTML(m.place));

  lines.push(
    `<button type="button" class="small-button" data-routes-user="${m.userId}">View routes</button>`
  );

  return lines.join('<br>');
}


// Show the members, places and active alerts of one circle
async function showCircle(circleId, fit = true) {
  const circle = await getJSON('/api/circles/' + circleId);
  const reopen = openPopupUser;

  redrawing = true;
  markers.clearLayers();
  placeLayer.clearLayers();
  redrawing = false;

  document.getElementById('user-circle').textContent =
    'Members: ' + circle.members.map((m) => m.firstName).join(', ');

  circle.places.forEach((p) => {
    L.circle([p.lat, p.lng], {
      radius: p.radius,
      color: '#555',
      weight: 1,
      fillOpacity: 0.1,
      interactive: false
    })
      .bindTooltip(escapeHTML(p.name), {
        permanent: true,
        direction: 'bottom',
        offset: [0, 8],
        className: 'place-label'
      })
      .addTo(placeLayer);
  });

  const points = [];

  circle.members.forEach((m) => {
    memberNames[m.userId] = m.firstName;

    if (m.lat === null || m.lng === null) return;

    const color = m.userId === currentUserId ? 'blue' : 'green';

    const marker = L.marker([m.lat, m.lng], { icon: pin(m.firstName, color) })
      .bindPopup(popupHTML(m))
      .addTo(markers);

    marker.on('popupopen', () => {
      openPopupUser = m.userId;
    });

    marker.on('popupclose', () => {
      if (!redrawing && openPopupUser === m.userId) openPopupUser = null;
    });

    // The map redraws every few seconds, so keep an open popup open
    if (m.userId === reopen) marker.openPopup();

    points.push([m.lat, m.lng]);
  });

  circle.alerts.forEach((a) => {
    if (a.lat === null || a.lng === null) return;

    const when = new Date(a.time).toLocaleString();

    L.circleMarker([a.lat, a.lng], { radius: 9, color: 'red' })
      .bindPopup(`${escapeHTML(a.firstName)}: ${escapeHTML(a.name)}<br>${when}`)
      .addTo(markers);
  });

  if (fit && points.length > 0) {
    map.fitBounds(points, { padding: [120, 200] });
  }
}

function refreshCircle() {
  if (circleSelect.value) {
    showCircle(circleSelect.value, false).catch(() => {});
  }
}


// Popup messages for notifications
const toasts = document.getElementById('toasts');
let lastNotificationId = null;

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  toasts.appendChild(toast);
  setTimeout(() => toast.remove(), 7000);

  // Also use the system notification when the tab is in the background
  if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
    new Notification('Safety Circles', { body: message });
  }
}

async function pollNotifications() {
  const first = lastNotificationId === null;
  const url = first ? '/api/notifications' : '/api/notifications?after=' + lastNotificationId;
  const data = await getJSON(url);

  // Old notifications only show up in the list, not as popups
  if (!first) data.items.forEach((n) => showToast(n.message));

  lastNotificationId = data.lastId;
}


// Send this device's location, speed and battery so the circle can see them
const locationStatus = document.getElementById('location-status');
let firstFix = true;

function locationFailed(error) {
  locationStatus.textContent = 'Your location is unavailable: ' + error.message;
}

async function sendLocation(position) {
  locationStatus.textContent = '';

  const c = position.coords;

  const res = await send('/api/location', {
    lat: c.latitude,
    lng: c.longitude,
    speed: c.speed === null ? null : c.speed * 2.23694,
    battery: await getBatteryLevel()
  });

  if (res.ok && circleSelect.value) {
    await showCircle(circleSelect.value, firstFix);
    firstFix = false;
  }
}


// Load the signed-in user and their circles from the backend
async function load() {
  const user = await getJSON('/api/user');

  currentUserId = user.userId;
  document.getElementById('user-name').textContent = user.name;

  user.circles.forEach((c) => circleSelect.add(new Option(c.name, c.circleId)));

  circleSelect.addEventListener('change', () => {
    routeLayer.clearLayers();
    showCircle(circleSelect.value);
  });

  if (user.circles.length > 0) {
    await showCircle(circleSelect.value);
  }

  await pollNotifications();

  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(sendLocation, locationFailed);
  } else {
    locationStatus.textContent = 'Your browser does not support location.';
  }
}

load().catch(() => {
  document.getElementById('user-name').textContent = 'Could not load data';
});

// Everyone else's pins and notifications update every few seconds
setInterval(() => {
  refreshCircle();
  pollNotifications().catch(() => {});
}, 10000);


// SOS panel controls
const sosButton = document.getElementById('sos-button');
const sosPanel = document.getElementById('sos-panel');

const sosConfirmation = document.getElementById('sos-confirmation');
const sosActive = document.getElementById('sos-active');

const closeSos = document.getElementById('close-sos');
const cancelSos = document.getElementById('cancel-sos');
const confirmSos = document.getElementById('confirm-sos');
const stopSos = document.getElementById('stop-sos');

function openSosPanel() {
  sosPanel.classList.remove('hidden');
  sosConfirmation.classList.remove('hidden');
  sosActive.classList.add('hidden');
}

function closeSosPanel() {
  sosPanel.classList.add('hidden');
}

sosButton.addEventListener('click', openSosPanel);

closeSos.addEventListener('click', closeSosPanel);
cancelSos.addEventListener('click', closeSosPanel);


// Activate SOS: save an alert for the selected circle
confirmSos.addEventListener('click', async () => {
  sosConfirmation.classList.add('hidden');
  sosActive.classList.remove('hidden');

  const locationText = document.getElementById('sos-location');
  const accuracyText = document.getElementById('sos-accuracy');
  const batteryText = document.getElementById('sos-battery');
  const statusText = document.getElementById('sos-status');

  locationText.textContent = 'Getting location...';
  accuracyText.textContent = 'Checking GPS...';
  batteryText.textContent = 'Checking battery...';
  statusText.textContent = 'Sending alert...';

  const position = await getPosition();

  if (position) {
    const { latitude, longitude, accuracy } = position.coords;

    locationText.textContent = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
    accuracyText.textContent = `Within ${Math.round(accuracy)} metres`;

    L.circleMarker([latitude, longitude], {
      radius: 9,
      color: 'red'
    }).addTo(map).bindPopup('Your current location').openPopup();

    map.setView([latitude, longitude], 15);
  } else {
    locationText.textContent = 'Location unavailable';
    accuracyText.textContent = 'GPS permission denied or unavailable';
  }

  // The alert goes out even if the location could not be found
  const circleName = circleSelect.options[circleSelect.selectedIndex].text;

  try {
    const res = await send('/api/alerts', {
      circleId: Number(circleSelect.value),
      lat: position ? position.coords.latitude : null,
      lng: position ? position.coords.longitude : null
    });

    statusText.textContent = res.ok
      ? 'Alert sent to ' + circleName + '.'
      : 'Could not send the alert.';

    refreshCircle();
  } catch {
    statusText.textContent = 'Could not send the alert.';
  }

  const battery = await getBatteryLevel();

  batteryText.textContent = battery === null
    ? 'Not supported by this browser'
    : battery + '%';
});


// Deactivate SOS: ends the alert for the circle
stopSos.addEventListener('click', async () => {
  await send('/api/alerts/resolve', {});

  sosActive.classList.add('hidden');
  sosConfirmation.classList.remove('hidden');

  refreshCircle();
});
