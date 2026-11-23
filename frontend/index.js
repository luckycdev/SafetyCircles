const circleSelect = document.getElementById('circle-select');


// Small helpers for talking to the backend
async function getJSON(url) {
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Request failed: ' + url);
  }

  return res.json();
}

function postJSON(url, data) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
}

function escapeHTML(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
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


// Navigation between Map, Places, and Settings
const tabs = document.querySelectorAll('.tabs button');
const panels = document.querySelectorAll('.floating-panel');

async function showPanel(name) {
  tabs.forEach((t) =>
    t.classList.toggle('active', t.dataset.panel === name)
  );

  panels.forEach((p) => p.classList.add('hidden'));

  if (name === 'map') return;

  const panel = document.getElementById(name + '-panel');

  if (!panel.innerHTML) {
    const res = await fetch('/' + name + '.html');
    panel.innerHTML = await res.text();
  }

  if (name === 'settings') {
    await loadSettings(panel);
  }

  panel.classList.remove('hidden');
}

tabs.forEach((t) =>
  t.addEventListener('click', () => showPanel(t.dataset.panel))
);

document.addEventListener('click', (e) => {
  if (e.target.closest('.close-panel')) showPanel('map');
});


// Settings are saved in the database whenever a toggle changes
async function loadSettings(panel) {
  const settings = await getJSON('/api/settings');

  panel.querySelectorAll('[data-setting]').forEach((box) => {
    box.checked = settings[box.dataset.setting];
  });
}

document.addEventListener('change', async (e) => {
  const setting = e.target.dataset.setting;

  if (!setting) return;

  const res = await postJSON('/api/settings', {
    setting: setting,
    value: e.target.checked
  });

  if (!res.ok) {
    e.target.checked = !e.target.checked;
  }
});


// Initialize Leaflet map
const map = L.map('map').setView([38.627, -90.1994], 11);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);


// Create map markers
function pin(name, color) {
  return L.divIcon({
    className: '',
    html: `<div class="pin"><span>${escapeHTML(name)}</span><i style="background:${color}"></i></div>`,
    iconSize: [120, 40],
    iconAnchor: [60, 38]
  });
}

const markers = L.layerGroup().addTo(map);
let currentUserId = null;


// Show the members and recent alerts of one circle
async function showCircle(circleId, fit = true) {
  const circle = await getJSON('/api/circles/' + circleId);

  markers.clearLayers();

  document.getElementById('user-circle').textContent =
    'Members: ' + circle.members.map((m) => m.firstName).join(', ');

  const points = [];

  circle.members.forEach((m) => {
    if (m.lat === null || m.lng === null) return;

    const color = m.userId === currentUserId ? 'blue' : 'green';

    L.marker([m.lat, m.lng], {
      icon: pin(m.firstName, color)
    }).addTo(markers);

    points.push([m.lat, m.lng]);
  });

  circle.alerts.forEach((a) => {
    if (a.lat === null || a.lng === null) return;

    const when = new Date(a.time + 'Z').toLocaleString();

    L.circleMarker([a.lat, a.lng], { radius: 9, color: 'red' })
      .bindPopup(`${escapeHTML(a.firstName)}: ${escapeHTML(a.name)}<br>${when}`)
      .addTo(markers);
  });

  if (fit && points.length > 0) {
    map.fitBounds(points, { padding: [120, 200] });
  }
}


// Send this device's location so the circle can see it
let firstFix = true;

const locationStatus = document.getElementById('location-status');

function locationFailed(error) {
  locationStatus.textContent = 'Your location is unavailable: ' + error.message;
}

async function sendLocation(position) {
  locationStatus.textContent = '';

  const res = await postJSON('/api/location', {
    lat: position.coords.latitude,
    lng: position.coords.longitude
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
  circleSelect.addEventListener('change', () => showCircle(circleSelect.value));

  if (user.circles.length > 0) {
    await showCircle(circleSelect.value);
  }

  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(sendLocation, locationFailed);
  } else {
    locationStatus.textContent = 'Your browser does not support location.';
  }
}

load().catch(() => {
  document.getElementById('user-name').textContent = 'Could not load data';
});


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
    const res = await postJSON('/api/alerts', {
      circleId: Number(circleSelect.value),
      lat: position ? position.coords.latitude : null,
      lng: position ? position.coords.longitude : null
    });

    statusText.textContent = res.ok
      ? 'Alert sent to ' + circleName + '.'
      : 'Could not send the alert.';
  } catch {
    statusText.textContent = 'Could not send the alert.';
  }

  // Get device battery level when supported
  if (navigator.getBattery) {
    try {
      const battery = await navigator.getBattery();
      batteryText.textContent = Math.round(battery.level * 100) + '%';
    } catch {
      batteryText.textContent = 'Unavailable';
    }
  } else {
    batteryText.textContent = 'Not supported by this browser';
  }
});


// Close the SOS screen on this device
stopSos.addEventListener('click', () => {
  sosActive.classList.add('hidden');
  sosConfirmation.classList.remove('hidden');
});
