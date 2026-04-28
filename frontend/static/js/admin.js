import { api } from './api.js';
import { esc } from './utils.js';

function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + type + ' show';
  setTimeout(() => el.classList.remove('show'), 3000);
}

async function loadStats() {
  const s = await api('GET', '/api/admin/stats');
  document.getElementById('statPills').innerHTML = `
    <div class="stat-pill"><span>Користувачі</span>${s.total_users}</div>
    <div class="stat-pill"><span>Активні</span>${s.active_users}</div>
    <div class="stat-pill"><span>Завантаження</span>${s.total_uploads}</div>
  `;
}

function fmtDt(iso) {
  if (!iso) return '—';
  return iso.slice(0, 19).replace('T', ' ');
}

async function loadUsers() {
  const users = await api('GET', '/api/admin/users');
  document.getElementById('usersBody').innerHTML = users
    .map(
      (u) => `
    <tr data-user-id="${u.id}">
      <td>${esc(u.username)}</td>
      <td>${esc(u.role)}</td>
      <td>${u.is_active ? 'активний' : 'вимкнено'}</td>
      <td>${u.use_admin_key ? 'глобал' : u.has_api_key ? 'свій' : '—'}</td>
      <td>${fmtDt(u.created_at)}</td>
      <td>${fmtDt(u.last_login_at)}</td>
      <td class="actions">
        <button type="button" class="btn-sm" data-action="toggle-active">Активність</button>
        <button type="button" class="btn-sm" data-action="reset-pw">Пароль</button>
        <button type="button" class="btn-sm" data-action="toggle-admin-key">Глобал ключ</button>
        <button type="button" class="btn-sm danger" data-action="delete-user">Видалити</button>
      </td>
    </tr>`,
    )
    .join('');
}

async function loadLogs() {
  const action = document.getElementById('logActionFilter').value.trim();
  const q = action ? `?action=${encodeURIComponent(action)}` : '';
  const logs = await api('GET', '/api/admin/logs' + q);
  document.getElementById('logsBody').innerHTML = logs
    .map(
      (l) => `
    <tr>
      <td>${l.id}</td>
      <td>${fmtDt(l.created_at)}</td>
      <td>${l.user_id || '—'}</td>
      <td>${esc(l.action)}</td>
      <td>${l.ip || '—'}</td>
    </tr>`,
    )
    .join('');
}

document.getElementById('usersBody').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const tr = btn.closest('tr');
  const userId = tr.dataset.userId;
  const action = btn.dataset.action;
  try {
    if (action === 'toggle-active') {
      await api('POST', `/api/admin/users/${userId}/toggle-active`);
      toast('Оновлено', 'success');
      await loadUsers();
    } else if (action === 'toggle-admin-key') {
      await api('POST', `/api/admin/users/${userId}/toggle-admin-key`);
      toast('Оновлено', 'success');
      await loadUsers();
    } else if (action === 'reset-pw') {
      const pw = prompt('Новий пароль (8+ символів):');
      if (!pw) return;
      await api('POST', `/api/admin/users/${userId}/reset-password`, { new_password: pw });
      toast('Пароль змінено', 'success');
    } else if (action === 'delete-user') {
      if (!confirm('Видалити користувача?')) return;
      await api('DELETE', `/api/admin/users/${userId}`);
      toast('Видалено', 'success');
      await loadUsers();
      await loadStats();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
});

document.getElementById('saveGlobalKeyBtn').addEventListener('click', async () => {
  const key = document.getElementById('globalKeyInput').value.trim();
  if (!key) {
    toast('Введіть ключ', 'error');
    return;
  }
  try {
    await api('POST', '/api/admin/global-key', { api_key: key });
    document.getElementById('globalKeyInput').value = '';
    toast('Збережено', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
});

document.getElementById('delGlobalKeyBtn').addEventListener('click', async () => {
  if (!confirm('Видалити глобальний ключ?')) return;
  try {
    await api('DELETE', '/api/admin/global-key');
    toast('Видалено', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
});

document.getElementById('saveRegBtn').addEventListener('click', async () => {
  const open = document.getElementById('regOpenToggle').checked;
  try {
    await api('POST', '/api/admin/settings/registration', { open });
    toast('Збережено', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
});

document.getElementById('reloadLogsBtn').addEventListener('click', () => loadLogs().catch((e) => toast(e.message, 'error')));

document.getElementById('adminLogout').addEventListener('click', async () => {
  await api('POST', '/api/auth/logout').catch(() => {});
  window.location.href = '/';
});

async function boot() {
  try {
    const me = await api('GET', '/api/auth/me');
    if (me.role !== 'admin') {
      window.location.href = '/dashboard';
      return;
    }
  } catch {
    window.location.href = '/';
    return;
  }
  document.getElementById('regOpenToggle').checked = true;
  try {
    await loadStats();
    await loadUsers();
    await loadLogs();
  } catch (e) {
    toast(e.message, 'error');
  }
}

boot();
