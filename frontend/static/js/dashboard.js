import { api } from './api.js';
import { buildCharts } from './charts.js';
import {
  applyFilters,
  bindFilterListeners,
  rebuildCategoryOptions,
  setAllTransactions,
} from './filters.js';
import { esc, fmt, fmtDate } from './utils.js';

let currentUser = null;
let currentUploadId = null;

function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + type + ' show';
  setTimeout(() => {
    el.classList.remove('show');
  }, 3000);
}

function setStatus(text, active) {
  document.getElementById('statusText').textContent = text;
  document.getElementById('statusDot').classList.toggle('active', active);
}

function showEmpty() {
  document.getElementById('empty-section').style.display = 'flex';
  document.getElementById('dashboard-section').style.display = 'none';
  setStatus('готовий', false);
}

function renderUserStats(s) {
  const wrap = document.getElementById('userStatsPanel');
  if (!wrap) return;

  if (!s || !s.uploads_considered) {
    wrap.innerHTML =
      '<div class="sidebar-stats-empty">Після завантаження виписок тут з’явиться сумарна статистика з усіх файлів.</div>';
    return;
  }

  const filtered =
    s.filter_date_from || s.filter_date_to
      ? `${s.filter_date_from ?? '…'} → ${s.filter_date_to ?? '…'}`
      : null;
  const span =
    s.actual_date_from && s.actual_date_to ? `${s.actual_date_from} → ${s.actual_date_to}` : '—';
  const periodLabel = filtered ? `Фільтр: ${filtered}` : `Період даних: ${span}`;

  const dupNote =
    s.duplicates_removed > 0
      ? `<div class="sidebar-stats-note">Виключено ${s.duplicates_removed} повторів між виписками (однакові дата, опис і сума в UAH).</div>`
      : '';

  wrap.innerHTML = `
    <div class="sidebar-stats-period">${esc(periodLabel)}</div>
    <div class="sidebar-stats-row"><span>Витрати</span><strong>${fmt(Number(s.total_expenses))} ₴</strong></div>
    <div class="sidebar-stats-row"><span>Надходження</span><strong>${fmt(Number(s.total_income))} ₴</strong></div>
    <div class="sidebar-stats-meta">${s.transactions_unique} унік. операцій · ${s.uploads_considered} завантажень${s.transactions_before_dedupe > s.transactions_unique ? ` · до дедуплікації ${s.transactions_before_dedupe}` : ''}</div>
    ${dupNote}
  `;
}

async function refreshUserStats() {
  try {
    const s = await api('GET', '/api/dashboard/stats');
    renderUserStats(s);
  } catch (e) {
    console.error(e);
  }
}

function showLoading(show, steps) {
  const overlay = document.getElementById('loading-overlay');
  overlay.classList.toggle('visible', show);
  if (show && steps) {
    ['step1', 'step2', 'step3', 'step4', 'step5'].forEach((id, i) => {
      const el = document.getElementById(id);
      el.className = 'loader-step';
      el.textContent = steps[i] || '';
      el.style.display = steps[i] ? '' : 'none';
    });
  }
}

function setStep(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = el.textContent.slice(2);
  if (state === 'done') {
    el.className = 'loader-step done';
    el.textContent = '✓ ' + text;
  } else if (state === 'active') {
    el.className = 'loader-step active';
  }
}

function buildDashboard(txs, aiResult) {
  if (!txs || !txs.length) {
    showEmpty();
    return;
  }

  setAllTransactions(txs);
  const expenses = txs.filter((t) => t.amount_uah < 0);
  const income = txs.filter((t) => t.amount_uah > 0);
  const totalExp = expenses.reduce((s, t) => s + Math.abs(t.amount_uah), 0);
  const totalInc = income.reduce((s, t) => s + t.amount_uah, 0);
  const months = [...new Set(txs.map((t) => t.date.slice(0, 7)))].sort();

  document.getElementById('periodLabel').textContent = months.length
    ? `${months[0]} → ${months[months.length - 1]}`
    : '—';
  document.getElementById('dashTitle').textContent = `${expenses.length} витрат · ${income.length} надходжень`;
  setStatus(`${txs.length} транзакцій`, true);

  const avgPerMonth = totalExp / (months.length || 1);
  const balance = totalInc - totalExp;
  const maxExpense =
    expenses.length > 0 ? Math.max(...expenses.map((t) => Math.abs(t.amount_uah))) : 0;
  const metricsGrid = document.getElementById('metricsGrid');
  metricsGrid.innerHTML = [
    {
      label: 'Всього витрачено',
      value: fmt(totalExp) + ' ₴',
      sub: `за ${months.length} міс`,
      cls: '',
    },
    {
      label: 'Середньо / місяць',
      value: fmt(avgPerMonth) + ' ₴',
      sub: `${expenses.length} операцій`,
      cls: 'danger',
    },
    {
      label: 'Загальні надходження',
      value: fmt(totalInc) + ' ₴',
      sub: `${income.length} операцій`,
      cls: 'success',
    },
    {
      label: 'Баланс',
      value: (balance >= 0 ? '+' : '') + fmt(balance) + ' ₴',
      sub: balance >= 0 ? 'профіцит' : 'дефіцит',
      cls: balance >= 0 ? 'success' : 'danger',
    },
    {
      label: 'Транзакцій / день',
      value: (expenses.length / Math.max(1, months.length * 30)).toFixed(1),
      sub: 'в середньому',
      cls: '',
    },
    {
      label: 'Найдорожча трата',
      value: (expenses.length ? fmt(maxExpense) : '0') + ' ₴',
      sub: '',
      cls: 'warn',
    },
  ]
    .map(
      (m) => `<div class="metric-card ${m.cls}">
    <div class="metric-label">${m.label}</div>
    <div class="metric-value">${m.value}</div>
    <div class="metric-sub">${m.sub}</div>
  </div>`,
    )
    .join('');

  buildCharts(txs);

  const aiEl = document.getElementById('aiAnalysis');
  if (aiResult && aiResult.analysis) {
    aiEl.textContent = aiResult.analysis;
  } else {
    aiEl.textContent =
      'AI аналіз недоступний. Переконайтесь, що налаштований OpenAI API ключ.';
  }

  const recsCard = document.getElementById('recsCard');
  const recsGrid = document.getElementById('recsGrid');
  if (aiResult && aiResult.recommendations && aiResult.recommendations.length) {
    recsCard.style.display = 'block';
    recsGrid.innerHTML = aiResult.recommendations
      .map((r) => {
        const cls = r.type === 'cut' ? 'cut' : r.type === 'watch' ? 'watch' : 'ok';
        const tag =
          r.type === 'cut' ? '✂ МОЖНА СКОРОТИТИ' : r.type === 'watch' ? '⚠ СЛІДКУЙ' : '✓ ОК';
        return `<div class="rec-card ${cls}">
        <div class="rec-tag">${tag}</div>
        <div class="rec-title">${esc(r.title)}</div>
        <div class="rec-desc">${esc(r.desc)}</div>
        ${r.saving_uah ? `<div class="rec-amount">-${fmt(r.saving_uah)} ₴/міс</div>` : ''}
      </div>`;
      })
      .join('');
  } else {
    recsCard.style.display = 'none';
  }

  const subsCard = document.getElementById('subsCard');
  const subsGrid = document.getElementById('subsGrid');
  if (aiResult && aiResult.subscriptions && aiResult.subscriptions.length) {
    subsCard.style.display = 'block';
    subsGrid.innerHTML = aiResult.subscriptions
      .map((s) => {
        const cls = s.verdict === 'cut' ? 'cut' : s.verdict === 'review' ? 'watch' : 'ok';
        const tag =
          s.verdict === 'cut'
            ? '✂ ВІДПИСАТИСЯ'
            : s.verdict === 'review'
              ? '? ПОДУМАТИ'
              : '✓ ЗАЛИШИТИ';
        const period =
          s.period === 'monthly'
            ? 'Щомісячно'
            : s.period === 'yearly'
              ? 'Щорічно'
              : 'Невизначено';
        return `<div class="rec-card ${cls}">
        <div class="rec-tag">${tag}</div>
        <div class="rec-title">${esc(s.name)}</div>
        <div class="rec-desc">${period}</div>
        <div class="rec-amount">${fmt(s.amount_uah)} ₴</div>
      </div>`;
      })
      .join('');
  } else {
    subsCard.style.display = 'none';
  }

  rebuildCategoryOptions(txs);
  applyFilters();

  document.getElementById('empty-section').style.display = 'none';
  document.getElementById('dashboard-section').style.display = 'block';
}

async function loadUploads() {
  try {
    const uploads = await api('GET', '/api/dashboard/uploads');
    renderUploadsList(uploads);
  } catch (e) {
    console.error(e);
  }
}

function renderUploadsList(uploads) {
  const list = document.getElementById('uploadsList');
  const empty = document.getElementById('uploadsEmpty');
  list.innerHTML = '';

  if (!uploads || !uploads.length) {
    list.appendChild(empty);
    return;
  }

  uploads.forEach((u) => {
    const fmtClass = 'fmt-' + (u.file_format || 'xlsx');
    const dateStr = u.date_from ? `${u.date_from} – ${u.date_to || '…'}` : fmtDate(u.created_at);
    const item = document.createElement('div');
    item.className = 'upload-item' + (u.id === currentUploadId ? ' active' : '');
    item.dataset.id = u.id;
    item.innerHTML = `
      <div class="upload-item-name">${esc(u.filename)}</div>
      <div class="upload-item-meta">
        <span class="fmt-badge ${fmtClass}">${u.file_format || 'xlsx'}</span>
        <span>${u.tx_count} тр.</span>
        <span>${dateStr}</span>
      </div>
      <button type="button" class="upload-item-del" title="Видалити" data-action="delete-upload" data-id="${u.id}">✕</button>
    `;
    list.appendChild(item);
  });
}

async function openUpload(id) {
  currentUploadId = id;
  document.querySelectorAll('.upload-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });

  showLoading(true, [
    '○ завантажуємо транзакції...',
    '○ отримуємо AI аналіз...',
    null,
    null,
    '○ будуємо дашборд...',
  ]);

  try {
    setStep('step1', 'active');
    const data = await api('GET', `/api/dashboard/uploads/${id}`);
    setStep('step1', 'done');

    setStep('step5', 'active');
    buildDashboard(data.transactions, data.ai_result);
    setStep('step5', 'done');
  } catch (e) {
    toast('Помилка завантаження: ' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

async function deleteUpload(id) {
  if (!confirm('Видалити це завантаження?')) return;
  try {
    await api('DELETE', `/api/dashboard/uploads/${id}`);
    if (currentUploadId === id) {
      currentUploadId = null;
      showEmpty();
    }
    await loadUploads();
    await refreshUserStats();
    toast('Завантаження видалено', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function setupDrop() {
  const overlay = document.getElementById('dropOverlay');

  document.addEventListener('dragenter', (e) => {
    if (e.dataTransfer.types.includes('Files')) {
      e.preventDefault();
      overlay.classList.add('visible');
    }
  });
  document.addEventListener('dragleave', (e) => {
    if (!e.relatedTarget || e.relatedTarget === document.documentElement) {
      overlay.classList.remove('visible');
    }
  });
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', (e) => {
    e.preventDefault();
    overlay.classList.remove('visible');
    handleFiles(e.dataTransfer.files);
  });

  const dzBig = document.getElementById('dropZoneBig');
  dzBig.addEventListener('dragover', (e) => {
    e.preventDefault();
    dzBig.classList.add('drag-over');
  });
  dzBig.addEventListener('dragleave', () => dzBig.classList.remove('drag-over'));
  dzBig.addEventListener('drop', (e) => {
    e.preventDefault();
    dzBig.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
  });

  document.getElementById('mainFileInput').addEventListener('change', (e) =>
    handleFiles(e.target.files),
  );
  document.getElementById('sidebarFileInput').addEventListener('change', (e) =>
    handleFiles(e.target.files),
  );
}

async function handleFiles(files) {
  if (!files || !files.length) return;

  const allowed = ['xlsx', 'xls', 'csv', 'pdf'];
  const valid = Array.from(files).filter((f) => {
    const ext = f.name.split('.').pop().toLowerCase();
    return allowed.includes(ext);
  });

  if (!valid.length) {
    toast('Непідтримуваний формат файлу. Використовуйте XLSX, CSV або PDF.', 'error');
    return;
  }

  showLoading(true, [
    '○ завантажуємо файли...',
    '○ парсимо транзакції...',
    '○ запускаємо AI аналіз...',
    '○ отримуємо рекомендації...',
    '○ будуємо дашборд...',
  ]);
  setStep('step1', 'active');

  try {
    const fd = new FormData();
    valid.forEach((f) => fd.append('files', f));

    setStatus('завантаження...', false);
    const result = await api('POST', '/api/analyze', fd);
    setStep('step1', 'done');
    setStep('step2', 'done');
    setStep('step3', 'active');

    currentUploadId = result.upload_id;
    await loadUploads();
    await refreshUserStats();

    setStep('step3', 'done');
    setStep('step4', 'active');

    const data = await api('GET', `/api/dashboard/uploads/${result.upload_id}`);
    setStep('step4', 'done');
    setStep('step5', 'active');

    buildDashboard(data.transactions, data.ai_result);
    setStep('step5', 'done');
    setStatus(`${data.transactions.length} транзакцій`, true);
    toast('Аналіз завершено', 'success');
  } catch (e) {
    toast('Помилка: ' + e.message, 'error');
    setStatus('помилка', false);
  } finally {
    showLoading(false);
    document.getElementById('mainFileInput').value = '';
    document.getElementById('sidebarFileInput').value = '';
  }
}

function openApiKeyModal() {
  const hasKey = currentUser && currentUser.has_api_key;
  const useAdmin = currentUser && currentUser.use_admin_key;

  document.getElementById('apiKeyInput').value = '';
  document.getElementById('apiKeyDeleteBtn').style.display = hasKey ? 'block' : 'none';
  document.getElementById('apiKeyCurrentRow').style.display = hasKey ? 'block' : 'none';

  if (useAdmin) {
    document.getElementById('apiKeyModalSub').textContent =
      'Ви використовуєте глобальний ключ адміністратора.';
  } else if (hasKey) {
    document.getElementById('apiKeyCurrentDisplay').textContent =
      currentUser.api_key_masked || 'sk-...****';
    document.getElementById('apiKeyModalSub').textContent = 'Поточний ключ:';
  } else {
    document.getElementById('apiKeyModalSub').textContent =
      'Ключ зберігається зашифрованим на сервері.';
  }

  document.getElementById('apiKeyModal').classList.add('visible');
}

function closeApiKeyModal() {
  document.getElementById('apiKeyModal').classList.remove('visible');
}

async function saveApiKey() {
  const key = document.getElementById('apiKeyInput').value.trim();
  if (!key) {
    toast('Введіть API ключ', 'error');
    return;
  }
  try {
    await api('POST', '/api/dashboard/api-key', { api_key: key });
    currentUser.has_api_key = true;
    closeApiKeyModal();
    toast('API ключ збережено', 'success');
    currentUser = await api('GET', '/api/auth/me');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteApiKey() {
  if (!confirm('Видалити API ключ?')) return;
  try {
    await api('DELETE', '/api/dashboard/api-key');
    currentUser.has_api_key = false;
    closeApiKeyModal();
    toast('API ключ видалено', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function logout() {
  await api('POST', '/api/auth/logout').catch(() => {});
  window.location.href = '/';
}

async function init() {
  try {
    const me = await api('GET', '/api/auth/me');
    currentUser = me;
    document.getElementById('usernameDisplay').textContent = me.username;
    document.getElementById('roleBadge').textContent = me.role;
    const adminLink = document.getElementById('adminLink');
    if (adminLink) {
      adminLink.style.display = me.role === 'admin' ? 'inline-flex' : 'none';
    }
    setStatus('готовий', false);
    await loadUploads();
    await refreshUserStats();
  } catch {
    window.location.href = '/';
  }
}

document.getElementById('uploadsList').addEventListener('click', (e) => {
  const del = e.target.closest('[data-action="delete-upload"]');
  if (del) {
    e.stopPropagation();
    deleteUpload(del.dataset.id);
    return;
  }
  const item = e.target.closest('.upload-item');
  if (item && item.dataset.id) {
    openUpload(item.dataset.id);
  }
});

document.getElementById('apiKeyBtn').addEventListener('click', () => openApiKeyModal());
document.getElementById('logoutBtn').addEventListener('click', () => logout());
document.getElementById('apiKeyModal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('apiKeyModal')) closeApiKeyModal();
});
document.getElementById('apiKeyDeleteBtn').addEventListener('click', () => deleteApiKey());
document.getElementById('apiKeyCancelBtn').addEventListener('click', () => closeApiKeyModal());
document.getElementById('apiKeySaveBtn').addEventListener('click', () => saveApiKey());

bindFilterListeners();
setupDrop();
init();
