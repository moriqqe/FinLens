import { api } from './api.js';

const authError = document.getElementById('authError');
const tabLogin = document.getElementById('tabLogin');
const tabRegister = document.getElementById('tabRegister');
const panelLogin = document.getElementById('panelLogin');
const panelRegister = document.getElementById('panelRegister');
const regClosedNote = document.getElementById('regClosedNote');

function showErr(msg) {
  authError.textContent = msg || '';
}

function setTab(name) {
  tabLogin.classList.toggle('active', name === 'login');
  tabRegister.classList.toggle('active', name === 'register');
  panelLogin.classList.toggle('active', name === 'login');
  panelRegister.classList.toggle('active', name === 'register');
  showErr('');
}

tabLogin.addEventListener('click', () => setTab('login'));
tabRegister.addEventListener('click', () => setTab('register'));

document.getElementById('btnLogin').addEventListener('click', async () => {
  showErr('');
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  try {
    await api('POST', '/api/auth/login', { username, password });
    window.location.href = '/dashboard';
  } catch (e) {
    showErr(e.message);
  }
});

document.getElementById('btnRegister').addEventListener('click', async () => {
  showErr('');
  const username = document.getElementById('regUser').value.trim();
  const password = document.getElementById('regPass').value;
  try {
    await api('POST', '/api/auth/register', { username, password });
    await api('POST', '/api/auth/login', { username, password });
    window.location.href = '/dashboard';
  } catch (e) {
    showErr(e.message);
    if (e.message.includes('closed') || e.message.includes('403')) {
      regClosedNote.style.display = 'block';
    }
  }
});

async function boot() {
  try {
    await api('GET', '/api/auth/me', undefined, { redirectOn401: false });
    window.location.href = '/dashboard';
  } catch {
    /* stay */
  }
}

boot();
