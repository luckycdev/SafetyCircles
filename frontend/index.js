const tabs = document.querySelectorAll('.tabs button');
const panels = document.querySelectorAll('.floating-panel');

async function showPanel(name) {
  tabs.forEach((t) => t.classList.toggle('active', t.dataset.panel === name));
  panels.forEach((p) => p.classList.add('hidden'));
  if (name === 'map') return;

  const panel = document.getElementById(name + '-panel');
  if (!panel.innerHTML) {
    const res = await fetch('/' + name + '.html');
    panel.innerHTML = await res.text();
  }
  panel.classList.remove('hidden');
}

tabs.forEach((t) => t.addEventListener('click', () => showPanel(t.dataset.panel)));
document.addEventListener('click', (e) => {
  if (e.target.closest('.close-panel')) showPanel('map');
});

const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

function pin(name, color) {
  return L.divIcon({
    className: '',
    html: `<div class="pin"><span>${name}</span><i style="background:${color}"></i></div>`,
    iconSize: [120, 40],
    iconAnchor: [60, 38]
  });
}

async function load() {
  const res = await fetch('/api/user');
  const data = await res.json();

  document.getElementById('user-name').textContent = data.name;
  document.getElementById('user-city').textContent = data.city;
  document.getElementById('user-circle').textContent =
    'Circle: ' + data.circle.map((p) => p.name).join(', ');

  const points = data.circle.map((p) => {
    const color = p.name === data.name ? 'blue' : 'green';
    L.marker([p.lat, p.lng], { icon: pin(p.name, color) }).addTo(map);
    return [p.lat, p.lng];
  });
  map.fitBounds(points, { padding: [50, 50] });
}

load().catch(() => {
  document.getElementById('user-name').textContent = 'Could not load data';
  map.setView([38.627, -90.1994], 11);
});
