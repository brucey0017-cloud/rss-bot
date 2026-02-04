const state = { items: [], sources: [] };
const listEl = document.getElementById('list');
const statsEl = document.getElementById('stats');
const searchEl = document.getElementById('search');
const sourceFilter = document.getElementById('sourceFilter');

function fmtDate(value) {
  if (!value) return 'Unknown time';
  const d = new Date(value);
  return d.toLocaleString();
}

function renderStats(items) {
  const last = items[0]?.published_at;
  statsEl.textContent = `${items.length} items · last update ${fmtDate(last)}`;
}

function renderList(items) {
  if (!items.length) {
    listEl.innerHTML = '<div class="empty">No items match.</div>';
    return;
  }
  listEl.innerHTML = items.map(item => `
    <article class="card">
      <h3><a href="${item.link}" target="_blank" rel="noopener noreferrer">${item.title}</a></h3>
      <p>${item.summary || ''}</p>
      <div class="meta">${item.source} · ${fmtDate(item.published_at)}</div>
    </article>
  `).join('');
}

function applyFilters() {
  const q = searchEl.value.toLowerCase();
  const s = sourceFilter.value;
  const filtered = state.items.filter(item => {
    const matchesQuery = !q || item.title.toLowerCase().includes(q) || (item.summary || '').toLowerCase().includes(q);
    const matchesSource = !s || item.source === s;
    return matchesQuery && matchesSource;
  });
  renderStats(filtered);
  renderList(filtered);
}

function fillSources(items) {
  const sources = Array.from(new Set(items.map(i => i.source))).sort();
  state.sources = sources;
  sourceFilter.innerHTML = '<option value="">All sources</option>' + sources.map(s => `<option value="${s}">${s}</option>`).join('');
}

async function load() {
  const res = await fetch('data.json', { cache: 'no-store' });
  const data = await res.json();
  state.items = data.items || [];
  fillSources(state.items);
  applyFilters();
}

searchEl.addEventListener('input', applyFilters);
sourceFilter.addEventListener('change', applyFilters);
load();
