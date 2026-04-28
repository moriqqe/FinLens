import { esc, fmt } from './utils.js';

let allTransactions = [];
let filteredTransactions = [];
let currentPage = 1;
const PAGE_SIZE = 20;

export function setAllTransactions(txs) {
  allTransactions = txs.sort((a, b) => new Date(b.date) - new Date(a.date));
}

export function applyFilters() {
  const search = document.getElementById('txSearch').value.toLowerCase();
  const cat = document.getElementById('catFilter').value;
  const type = document.getElementById('typeFilter').value;

  filteredTransactions = allTransactions.filter((t) => {
    if (search && !(t.description || '').toLowerCase().includes(search)) return false;
    if (cat && (t.category || 'Інше') !== cat) return false;
    if (type === 'expense' && t.amount_uah >= 0) return false;
    if (type === 'income' && t.amount_uah <= 0) return false;
    return true;
  });

  renderTable(1);
}

export function renderTable(page) {
  currentPage = page;
  const total = filteredTransactions.length;
  document.getElementById('txSubtitle').textContent = `${total} транзакцій`;
  const start = (page - 1) * PAGE_SIZE;
  const slice = filteredTransactions.slice(start, start + PAGE_SIZE);
  document.getElementById('txBody').innerHTML = slice
    .map((t) => {
      const neg = t.amount_uah < 0;
      return `<tr>
      <td style="color:var(--muted);font-family:var(--mono);font-size:11px">${t.date}</td>
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis">${esc(t.description || '—')}</td>
      <td><span class="cat-pill">${esc(t.category || 'Інше')}</span></td>
      <td class="td-amount ${neg ? 'neg' : 'pos'}" style="text-align:right">${neg ? '' : '+'} ${fmt(Math.abs(t.amount_uah))}</td>
      <td style="text-align:right;font-family:var(--mono);font-size:11px;color:var(--muted)">${esc(t.orig_currency || 'UAH')}</td>
    </tr>`;
    })
    .join('');

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pag = document.getElementById('pagination');
  let html = `<span>стор. ${page} / ${totalPages}</span>`;
  if (page > 1) html += `<button type="button" class="page-btn" data-page="${page - 1}">←</button>`;
  const s = Math.max(1, page - 2);
  const e = Math.min(totalPages, page + 2);
  for (let i = s; i <= e; i++) {
    html += `<button type="button" class="page-btn ${i === page ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }
  if (page < totalPages) html += `<button type="button" class="page-btn" data-page="${page + 1}">→</button>`;
  pag.innerHTML = html;
}

export function rebuildCategoryOptions(txs) {
  const catFilter = document.getElementById('catFilter');
  const cats = [...new Set(txs.map((t) => t.category || 'Інше'))].sort();
  catFilter.innerHTML =
    '<option value="">Всі категорії</option>' +
    cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
}

export function bindFilterListeners() {
  document.getElementById('txSearch').addEventListener('input', () => applyFilters());
  document.getElementById('catFilter').addEventListener('change', () => applyFilters());
  document.getElementById('typeFilter').addEventListener('change', () => applyFilters());
  document.getElementById('pagination').addEventListener('click', (e) => {
    const b = e.target.closest('[data-page]');
    if (!b) return;
    renderTable(parseInt(b.dataset.page, 10));
  });
}
