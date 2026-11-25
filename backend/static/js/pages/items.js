import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { itemCard, hydrateThumbs } from '../item-cards.js';
import { $, $$, debounce, showError, skeletons, emptyState, esc, inlineError } from '../ui.js';

const PER = 12;
const p0 = new URLSearchParams(location.search);
const state = { q: p0.get('q') || '', item_type: p0.get('item_type') || '', category_id: p0.get('category_id') || '', location_id: p0.get('location_id') || '', status: p0.get('status') || '', date_from: p0.get('date_from') || '', date_to: p0.get('date_to') || '', page: Math.max(1, Number(p0.get('page')) || 1) };

await initLayout({ active: state.item_type === 'LOST' ? 'lost' : state.item_type === 'FOUND' ? 'found' : 'items' });

const grid = $('#grid'), pager = $('#pager');
let ticket = 0;

function syncForm() {
  $('#q').value = state.q; $('#category').value = state.category_id; $('#location').value = state.location_id;
  $('#status').value = state.status; $('#date_from').value = state.date_from; $('#date_to').value = state.date_to;
  $$('#type-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.type === state.item_type)));
}

async function load() {
  const my = ++ticket;
  const qs = new URLSearchParams();
  Object.entries(state).forEach(([k, v]) => { if (v && !(k === 'page' && v === 1)) qs.set(k, v); });
  history.replaceState(null, '', location.pathname + (qs.toString() ? '?' + qs : ''));
  $('#filter-error').innerHTML = '';
  if (state.date_from && state.date_to && state.date_from > state.date_to) { inlineError($('#filter-error'), '"From" date must be on or before the "To" date.'); return; }

  grid.className = 'items-grid'; grid.innerHTML = skeletons(PER); pager.innerHTML = '';
  try {
    const d = await api.items({ ...state, page: state.page, per_page: PER });
    if (my !== ticket) return;
    if (!d.items.length) {
      grid.className = '';
      grid.innerHTML = emptyState(state.page > 1 ? 'No more results' : 'No items match your search', 'Try removing a filter or searching with different words.', '<button class="btn btn-secondary" id="clear2" type="button">Clear filters</button>');
      $('#clear2').addEventListener('click', clearAll);
    } else { grid.innerHTML = d.items.map(itemCard).join(''); hydrateThumbs(grid); }
    $('#summary').textContent = d.items.length ? `Showing ${(state.page - 1) * PER + 1}-${(state.page - 1) * PER + d.items.length}` : '';
    pager.innerHTML = state.page > 1 || d.items.length === PER
      ? `<button class="btn btn-secondary btn-sm" id="prev" ${state.page === 1 ? 'disabled' : ''}>Previous</button><span class="muted small">Page ${state.page}</span><button class="btn btn-secondary btn-sm" id="next" ${d.items.length < PER ? 'disabled' : ''}>Next</button>` : '';
    const go = (n) => { state.page = n; load(); window.scrollTo({ top: 0 }); };
    $('#prev') && $('#prev').addEventListener('click', () => go(state.page - 1));
    $('#next') && $('#next').addEventListener('click', () => go(state.page + 1));
  } catch (e) { if (my === ticket) { grid.className = ''; showError(grid, e, load); } }
}

function clearAll() { Object.keys(state).forEach((k) => { state[k] = k === 'page' ? 1 : ''; }); syncForm(); load(); }
const set = (k, v) => { state[k] = v; state.page = 1; load(); };

try {
  const meta = await api.meta();
  $('#category').innerHTML = '<option value="">All categories</option>' + meta.categories.map((c) => `<option value="${c.category_id}">${esc(c.category_name)}</option>`).join('');
  $('#location').innerHTML = '<option value="">All locations</option>' + meta.locations.map((l) => `<option value="${l.location_id}">${esc(l.location_name)}</option>`).join('');
} catch (e) { inlineError($('#filter-error'), 'Could not load category and location filters. ' + e.message); }

syncForm();
$('#q').addEventListener('input', debounce((e) => set('q', e.target.value.trim())));
$('#category').addEventListener('change', (e) => set('category_id', e.target.value));
$('#location').addEventListener('change', (e) => set('location_id', e.target.value));
$('#status').addEventListener('change', (e) => set('status', e.target.value));
$('#date_from').addEventListener('change', (e) => set('date_from', e.target.value));
$('#date_to').addEventListener('change', (e) => set('date_to', e.target.value));
$$('#type-seg button').forEach((b) => b.addEventListener('click', () => { set('item_type', b.dataset.type); syncForm(); }));
$('#clear').addEventListener('click', clearAll);
$('#filters').addEventListener('submit', (e) => e.preventDefault());
load();
