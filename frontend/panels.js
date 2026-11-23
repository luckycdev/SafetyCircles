// The Places, Settings, Account, Notifications and Routes panels
const tabs = document.querySelectorAll('.tabs button');
const panels = document.querySelectorAll('.floating-panel');

// Panels opened from another panel keep that panel's tab highlighted
const parentTab = { account: 'settings', notifications: 'settings', routes: 'map' };

const panelLoaders = {
  places: loadPlaces,
  settings: loadSettings,
  account: loadAccount,
  notifications: loadNotifications,
  routes: loadRoutes
};

const draftLayer = L.layerGroup().addTo(map);
const pickHint = document.getElementById('pick-hint');

let picking = false;
let draftSpot = null;
let routesUserId = null;
let loadedRoutes = [];


async function showPanel(name) {
  stopPicking(false);

  const tabName = parentTab[name] || name;

  tabs.forEach((t) =>
    t.classList.toggle('active', t.dataset.panel === tabName)
  );

  panels.forEach((p) => p.classList.add('hidden'));

  if (name === 'map') return;

  const panel = document.getElementById(name + '-panel');

  if (!panel.innerHTML) {
    const res = await fetch('/' + name + '.html');
    panel.innerHTML = await res.text();
  }

  await panelLoaders[name](panel);

  panel.classList.remove('hidden');
}

tabs.forEach((t) =>
  t.addEventListener('click', () => showPanel(t.dataset.panel))
);


// Clicks on buttons inside the panels and popups
document.addEventListener('click', (e) => {
  const open = e.target.closest('[data-open]');
  const action = e.target.closest('[data-action]');
  const showRouteButton = e.target.closest('[data-show-route]');
  const deleteButton = e.target.closest('[data-delete-place]');
  const demoButton = e.target.closest('[data-demo]');

  if (open) {
    e.preventDefault();
    showPanel(open.dataset.open);
  } else if (e.target.closest('.close-panel')) {
    showPanel('map');
  } else if (action) {
    runAction(action.dataset.action);
  } else if (showRouteButton) {
    showRoute(Number(showRouteButton.dataset.showRoute));
  } else if (deleteButton) {
    deletePlace(Number(deleteButton.dataset.deletePlace));
  } else if (demoButton) {
    runDemo(demoButton.dataset.demo);
  }
});

// Leaflet keeps clicks inside popups from reaching the page, so hook the button directly
map.on('popupopen', (e) => {
  const button = e.popup.getElement().querySelector('[data-routes-user]');

  if (button) {
    button.addEventListener('click', () => openRoutes(Number(button.dataset.routesUser)));
  }
});

document.addEventListener('submit', (e) => {
  e.preventDefault();

  if (e.target.id === 'place-form') savePlace(e.target);
  if (e.target.id === 'account-form') saveAccount(e.target);
  if (e.target.id === 'password-form') savePassword(e.target);
});


// Settings
async function loadSettings(panel) {
  const settings = await getJSON('/api/settings');

  panel.querySelectorAll('[data-setting]').forEach((box) => {
    box.checked = settings[box.dataset.setting];
  });
}

document.addEventListener('change', async (e) => {
  const setting = e.target.dataset.setting;

  if (!setting) return;

  const res = await send('/api/settings', {
    setting: setting,
    value: e.target.checked
  });

  if (!res.ok) {
    e.target.checked = !e.target.checked;
    return;
  }

  // Ask once for permission to show system notifications
  if (e.target.checked && setting !== 'pauseSharing' &&
      'Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
});

async function runDemo(action) {
  const status = document.getElementById('demo-status');
  const res = await send('/api/demo', { action: action });

  status.textContent = res.data.message || res.data.error || 'Done.';

  refreshCircle();
  pollNotifications().catch(() => {});
}


// Account
async function loadAccount(panel) {
  const account = await getJSON('/api/account');
  const form = panel.querySelector('#account-form');

  ['firstName', 'lastName', 'email', 'phoneNumber'].forEach((field) => {
    form.elements[field].value = account[field];
  });
}

async function saveAccount(form) {
  const status = document.getElementById('account-status');

  const res = await send('/api/account', {
    firstName: form.elements.firstName.value,
    lastName: form.elements.lastName.value,
    email: form.elements.email.value,
    phoneNumber: form.elements.phoneNumber.value
  });

  if (!res.ok) {
    status.textContent = res.data.error || 'Could not save your changes.';
    return;
  }

  status.textContent = 'Saved.';
  document.getElementById('user-name').textContent = res.data.name;
}

async function savePassword(form) {
  const status = document.getElementById('password-status');

  if (form.elements.new.value !== form.elements.repeat.value) {
    status.textContent = 'The new passwords do not match.';
    return;
  }

  const res = await send('/api/password', {
    current: form.elements.current.value,
    new: form.elements.new.value
  });

  if (!res.ok) {
    status.textContent = res.data.error || 'Could not change the password.';
    return;
  }

  form.reset();
  status.textContent = 'Password changed.';
}


// Notifications list
async function loadNotifications(panel) {
  const data = await getJSON('/api/notifications');
  const list = panel.querySelector('#notification-list');

  if (data.items.length === 0) {
    list.innerHTML = '<p class="muted">No notifications yet.</p>';
    return;
  }

  list.innerHTML = data.items.map((n) => `
    <div class="list-item">
      <div>
        ${escapeHTML(n.message)}<br>
        <span class="muted">${timeAgo(n.time)}</span>
      </div>
    </div>
  `).join('');
}


// Places
async function loadPlaces(panel) {
  const places = await getJSON('/api/places');
  const list = panel.querySelector('#place-list');

  if (places.length === 0) {
    list.innerHTML = '<p class="muted">No places yet.</p>';
  } else {
    list.innerHTML = places.map((p) => `
      <div class="list-item">
        <div>
          <strong>${escapeHTML(p.name)}</strong><br>
          <span class="muted">
            ${escapeHTML(p.circleName)}, ${Math.round(p.radius)} m${p.address ? ', ' + escapeHTML(p.address) : ''}
          </span>
        </div>
        ${p.canDelete ? `<button type="button" class="small-button" data-delete-place="${p.placeId}">Delete</button>` : ''}
      </div>
    `).join('');
  }

  showPlaceView('list');
}

function showPlaceView(view) {
  document.getElementById('place-list-view').classList.toggle('hidden', view !== 'list');
  document.getElementById('place-form').classList.toggle('hidden', view !== 'form');
}

function openPlaceForm() {
  const form = document.getElementById('place-form');

  form.reset();
  form.elements.circleId.innerHTML = circleSelect.innerHTML;
  form.elements.circleId.value = circleSelect.value;

  draftSpot = null;
  draftLayer.clearLayers();
  document.getElementById('place-spot').textContent = 'No spot chosen yet.';
  document.getElementById('place-error').textContent = '';

  showPlaceView('form');
}

function setDraft(lat, lng) {
  draftSpot = { lat: lat, lng: lng };

  draftLayer.clearLayers();
  L.circleMarker([lat, lng], { radius: 8, color: '#1d4ed8' }).addTo(draftLayer);

  document.getElementById('place-spot').textContent =
    'Chosen spot: ' + lat.toFixed(5) + ', ' + lng.toFixed(5);
}

function startPicking() {
  picking = true;
  document.getElementById('places-panel').classList.add('hidden');
  pickHint.classList.remove('hidden');
}

function stopPicking(showPanelAgain) {
  if (!picking) return;

  picking = false;
  pickHint.classList.add('hidden');

  if (showPanelAgain) {
    document.getElementById('places-panel').classList.remove('hidden');
  }
}

map.on('click', (e) => {
  if (picking) {
    setDraft(e.latlng.lat, e.latlng.lng);
    stopPicking(true);
  } else {
    routeLayer.clearLayers();
  }
});

// Looks an address up with OpenStreetMap's free search
async function findAddress() {
  const form = document.getElementById('place-form');
  const error = document.getElementById('place-error');
  const address = form.elements.address.value.trim();

  if (!address) {
    error.textContent = 'Type an address first.';
    return;
  }

  error.textContent = 'Searching...';

  try {
    const res = await fetch(
      'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' +
      encodeURIComponent(address)
    );
    const found = await res.json();

    if (found.length === 0) {
      error.textContent = 'Address not found.';
      return;
    }

    const lat = Number(found[0].lat);
    const lng = Number(found[0].lon);

    setDraft(lat, lng);
    map.setView([lat, lng], 16);
    error.textContent = '';
  } catch {
    error.textContent = 'Could not search for the address right now.';
  }
}

async function savePlace(form) {
  const error = document.getElementById('place-error');

  if (!draftSpot && form.elements.address.value.trim()) {
    await findAddress();
  }

  if (!draftSpot) {
    if (!form.elements.address.value.trim()) {
      error.textContent = 'Choose a spot: click the map or find an address.';
    }
    return;
  }

  const circleId = Number(form.elements.circleId.value);

  const res = await send('/api/places', {
    name: form.elements.name.value,
    circleId: circleId,
    radius: Number(form.elements.radius.value),
    address: form.elements.address.value,
    lat: draftSpot.lat,
    lng: draftSpot.lng
  });

  if (!res.ok) {
    error.textContent = res.data.error || 'Could not save the place.';
    return;
  }

  const spot = draftSpot;

  draftSpot = null;
  draftLayer.clearLayers();

  // Show the circle the place belongs to, with the new place on the map
  circleSelect.value = circleId;
  await showCircle(circleId, false);
  map.setView([spot.lat, spot.lng], 16);

  await showPanel('places');
}

async function deletePlace(placeId) {
  if (!confirm('Delete this place?')) return;

  const res = await send('/api/places/' + placeId, undefined, 'DELETE');

  if (res.ok) {
    await showPanel('places');
    refreshCircle();
  }
}

function runAction(action) {
  if (action === 'new-place') openPlaceForm();
  if (action === 'cancel-place') showPanel('places');
  if (action === 'pick-place') startPicking();
  if (action === 'cancel-pick') stopPicking(true);
  if (action === 'find-address') findAddress();
}


// Route history of one person
async function openRoutes(userId) {
  routesUserId = userId;
  map.closePopup();
  await showPanel('routes');
}

async function loadRoutes(panel) {
  const data = await getJSON('/api/users/' + routesUserId + '/routes');
  const list = panel.querySelector('#route-list');

  loadedRoutes = data.routes;
  panel.querySelector('#routes-title').textContent = data.name + "'s routes";

  if (data.routes.length === 0) {
    list.innerHTML = '<p class="muted">No drives yet.</p>';
    return;
  }

  list.innerHTML = data.routes.map((r) => {
    const when = new Date(r.startTime).toLocaleString([], {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
    const minutes = Math.max(1, Math.round(r.seconds / 60));

    return `
      <div class="list-item">
        <div>
          <strong>${when}${r.active ? ' (in progress)' : ''}</strong><br>
          <span class="muted">
            ${r.miles.toFixed(1)} mi, ${minutes} min, top speed ${Math.round(r.topSpeed)} mph
          </span>
        </div>
        <button type="button" class="small-button" data-show-route="${r.routeId}">Show</button>
      </div>
    `;
  }).join('');
}

// Draws a drive on the map. Only the start and end are saved, so the line is straight.
function showRoute(routeId) {
  const route = loadedRoutes.find((r) => r.routeId === routeId);

  if (!route) return;

  const start = [route.start.lat, route.start.lng];
  const end = [route.end.lat, route.end.lng];

  showPanel('map');

  routeLayer.clearLayers();
  L.polyline([start, end], { color: '#1d4ed8', weight: 4, dashArray: '6 8' }).addTo(routeLayer);
  L.circleMarker(start, { radius: 7, color: 'green' })
    .bindTooltip('Start', { permanent: true }).addTo(routeLayer);
  L.circleMarker(end, { radius: 7, color: 'red' })
    .bindTooltip('End', { permanent: true }).addTo(routeLayer);

  map.fitBounds([start, end], { padding: [120, 200], maxZoom: 16 });
}
