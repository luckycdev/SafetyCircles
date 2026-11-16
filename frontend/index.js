document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('status');
  const userName = document.getElementById('user-name');
  const userCircle = document.getElementById('user-circle');

  const loadBackendStatus = async () => {
    try {
      const response = await fetch('/api/health');
      const data = await response.json();
      statusEl.textContent = data.message;
    } catch (error) {
      statusEl.textContent = 'Backend is unavailable.';
    }
  };

  const loadUserData = async () => {
    try {
      const response = await fetch('/api/user');
      const data = await response.json();
      userName.textContent = data.name;
      userCircle.textContent = data.safetyCircle.join(', ');
    } catch (error) {
      statusEl.textContent = 'Unable to load user data.';
    }
  };

  loadBackendStatus();
  loadUserData();
});