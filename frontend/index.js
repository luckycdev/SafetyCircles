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

  panel.classList.remove('hidden');
}

tabs.forEach((t) =>
  t.addEventListener('click', () => showPanel(t.dataset.panel))
);

document.addEventListener('click', (e) => {
  if (e.target.closest('.close-panel')) showPanel('map');
});


// Initialize Leaflet map
const map = L.map('map');

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);


// Create map markers
function pin(name, color) {
  return L.divIcon({
    className: '',
    html: `<div class="pin"><span>${name}</span><i style="background:${color}"></i></div>`,
    iconSize: [120, 40],
    iconAnchor: [60, 38]
  });
}


// Load user and circle information
async function load() {
  const res = await fetch('/api/user');

  if (!res.ok) {
    throw new Error('Could not load user data');
  }

  const data = await res.json();

  document.getElementById('user-name').textContent = data.name;
  document.getElementById('user-city').textContent = data.city;
  document.getElementById('user-circle').textContent =
    'Members: ' + data.circle.map((p) => p.name).join(', ');

  const points = data.circle.map((p) => {
    const color = p.name === data.name ? 'blue' : 'green';

    L.marker([p.lat, p.lng], {
      icon: pin(p.name, color)
    }).addTo(map);

    return [p.lat, p.lng];
  });

  if (points.length > 0) {
    map.fitBounds(points, { padding: [50, 50] });
  } else {
    map.setView([38.627, -90.1994], 11);
  }
}

load().catch(() => {
  document.getElementById('user-name').textContent = 'Could not load data';
  map.setView([38.627, -90.1994], 11);
});


// Family circle selector
const circleSelect = document.getElementById('circle-select');

circleSelect.addEventListener('change', () => {
  const selectedCircle =
    circleSelect.options[circleSelect.selectedIndex].text;

  document.getElementById('user-circle').textContent =
    'Selected circle: ' + selectedCircle;

  // Demo only: actual circle switching requires backend support.
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


// Activate the demo SOS screen
confirmSos.addEventListener('click', async () => {
  sosConfirmation.classList.add('hidden');
  sosActive.classList.remove('hidden');

  const locationText = document.getElementById('sos-location');
  const accuracyText = document.getElementById('sos-accuracy');
  const batteryText = document.getElementById('sos-battery');

  locationText.textContent = 'Getting location...';
  accuracyText.textContent = 'Checking GPS...';
  batteryText.textContent = 'Checking battery...';

  // Get device location
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const latitude = position.coords.latitude;
        const longitude = position.coords.longitude;
        const accuracy = position.coords.accuracy;

        locationText.textContent =
          `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;

        accuracyText.textContent =
          `Within ${Math.round(accuracy)} metres`;

        L.circleMarker([latitude, longitude], {
          radius: 9,
          color: 'red'
        }).addTo(map).bindPopup('Your current location').openPopup();

        map.setView([latitude, longitude], 15);
      },
      () => {
        locationText.textContent = 'Location unavailable';
        accuracyText.textContent = 'GPS permission denied or unavailable';
      }
    );
  } else {
    locationText.textContent = 'Geolocation not supported';
    accuracyText.textContent = 'Unavailable';
  }

  // Get device battery level when supported
  if (navigator.getBattery) {
    try {
      const battery = await navigator.getBattery();
      batteryText.textContent =
        Math.round(battery.level * 100) + '%';
    } catch {
      batteryText.textContent = 'Unavailable';
    }
  } else {
    batteryText.textContent = 'Not supported by this browser';
  }
});


// Deactivate demo SOS mode
stopSos.addEventListener('click', () => {
  sosActive.classList.add('hidden');
  sosConfirmation.classList.remove('hidden');
});
