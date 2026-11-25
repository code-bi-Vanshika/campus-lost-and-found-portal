import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { icon } from '../icons.js';
import { $, $$, esc, param, todayISO, busy, inlineError, showError, toast } from '../ui.js';

const user = await initLayout({ active: 'report', requireAuth: true, roles: ['STUDENT', 'STAFF'] });
const MAX_BYTES = 2 * 1024 * 1024, TYPES = ['image/jpeg', 'image/png', 'image/webp'], MAX_FILES = 5;
const editId = Number(param('edit')) || 0;
let type = param('type') === 'FOUND' ? 'FOUND' : 'LOST';
let files = [];

$('#item_date').max = todayISO();
if (!editId) $('#item_date').value = todayISO();

function applyType() {
  const lost = type === 'LOST';
  $$('#type-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.type === type)));
  $('#page-title').textContent = editId ? 'Edit your report' : lost ? 'Report a lost item' : 'Report a found item';
  $('#page-sub').textContent = lost ? 'Describe what you lost so other students and staff can recognise it.' : 'Describe what you found. Keep one identifying detail back so you can verify the real owner.';
  $('#date-label').textContent = lost ? 'Date lost' : 'Date found';
  $('#loc-label').textContent = lost ? 'Where did you lose it?' : 'Where did you find it?';
  $('#found-tip').classList.toggle('hidden', lost);
  $('#submit').textContent = editId ? 'Save changes' : lost ? 'Report lost item' : 'Report found item';
}

function renderPreviews() {
  const g = $('#previews'); g.innerHTML = '';
  files.forEach((f, i) => {
    const d = document.createElement('div'); d.className = 'up';
    const img = new Image(); img.alt = f.name; img.src = URL.createObjectURL(f); img.onload = () => URL.revokeObjectURL(img.src);
    const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-label', 'Remove ' + f.name); b.innerHTML = '&times;';
    b.addEventListener('click', () => { files.splice(i, 1); renderPreviews(); });
    d.append(img, b); g.appendChild(d);
  });
  $('#img-count').textContent = files.length ? `${files.length} of ${MAX_FILES} photos` : '';
}
function addFiles(list) {
  const errs = [];
  [...list].forEach((f) => {
    if (!TYPES.includes(f.type)) errs.push(`${f.name}: use a JPEG, PNG or WebP image.`);
    else if (f.size > MAX_BYTES) errs.push(`${f.name}: larger than 2 MB.`);
    else if (files.length >= MAX_FILES) errs.push(`Only ${MAX_FILES} photos are allowed.`);
    else if (!files.some((x) => x.name === f.name && x.size === f.size && x.lastModified === f.lastModified)) files.push(f);
  });
  inlineError($('#img-error'), errs.join(' '));
  renderPreviews();
}

try {
  const meta = await api.meta();
  $('#category').innerHTML = '<option value="">Select a category</option>' + meta.categories.map((c) => `<option value="${c.category_id}">${esc(c.category_name)}</option>`).join('');
  $('#location').innerHTML = '<option value="">Select a location</option>' + meta.locations.map((l) => `<option value="${l.location_id}">${esc(l.location_name)}</option>`).join('');
} catch (e) { showError($('#form-error'), e); }

if (editId) {
  $('#type-field').classList.add('hidden'); $('#image-field').classList.add('hidden');
  try {
    const item = (await api.item(editId)).item;
    let owner = false;
    try { await api.itemClaims(editId); owner = true; } catch (e) { if (e.status !== 403) throw e; }
    if (!owner) { $('#form-error').innerHTML = '<div class="alert alert-error">You can only edit your own reports.</div>'; $('#report-form').classList.add('hidden'); }
    else if (item.status !== 'ACTIVE') { $('#form-error').innerHTML = '<div class="alert alert-warn">Only open reports can be edited.</div>'; $('#report-form').classList.add('hidden'); }
    type = item.item_type;
    $('#title').value = item.title; $('#description').value = item.description; $('#item_date').value = item.item_date;
    $('#category').value = item.category.category_id; $('#location').value = item.location.location_id;
  } catch (e) { showError($('#form-error'), e); $('#report-form').classList.add('hidden'); }
}
applyType();
$$('#type-seg button').forEach((b) => b.addEventListener('click', () => { type = b.dataset.type; applyType(); }));
const upd = () => { $('#title-count').textContent = $('#title').value.length + ' / 150'; };
$('#title').addEventListener('input', upd); upd();

const dz = $('#dropzone'), fi = $('#images');
dz.addEventListener('click', () => fi.click());
dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fi.click(); } });
dz.addEventListener('dragover', (e) => e.preventDefault());
dz.addEventListener('drop', (e) => { e.preventDefault(); addFiles(e.dataTransfer.files); });
fi.addEventListener('change', () => { addFiles(fi.files); fi.value = ''; });

$('#report-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const v = { title: $('#title').value.trim(), description: $('#description').value.trim(), category_id: $('#category').value, location_id: $('#location').value, item_date: $('#item_date').value };
  const problem = !v.title ? 'Enter a short title.' : v.title.length > 150 ? 'Title must be 150 characters or fewer.' : !v.category_id ? 'Choose a category.' : !v.location_id ? 'Choose a location.' : !v.item_date ? 'Choose a date.' : v.item_date > todayISO() ? 'The date cannot be in the future.' : !v.description ? 'Add a description.' : '';
  if (problem) { inlineError($('#form-error'), problem); window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
  inlineError($('#form-error'), '');
  busy($('#submit'), async () => {
    try {
      if (editId) {
        await api.editItem(editId, { ...v, category_id: Number(v.category_id), location_id: Number(v.location_id) });
        toast('Report updated.', 'ok'); api.clearItemCache(); location.href = 'item.html?id=' + editId;
      } else {
        const fd = new FormData();
        Object.entries(v).forEach(([k, val]) => fd.append(k, val));
        fd.append('item_type', type);
        files.forEach((f) => fd.append('images', f));
        const res = await api.createItem(fd);
        location.href = 'item.html?id=' + res.item_id;
      }
    } catch (err) { inlineError($('#form-error'), err.message); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  });
});
