import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { icon } from '../icons.js';
import { renderClaimCard, attachHandovers, claimStage } from '../claims-ui.js';
import { $, esc, fmtDate, itemStatusBadge, typeTag, param, showError, emptyState, toast, busy, confirmBox, inlineError, skeletons } from '../ui.js';

const user = await initLayout({ active: 'items' });
const id = Number(param('id'));
const root = $('#item-root');
let item = null;

function gallery(images) {
  if (!images.length) return `<div class="gallery-main">${icon('image', 56)}</div>`;
  return `<div class="gallery-main"><img id="main-img" src="${images[0].url}" alt="Photo of the item"></div>
    ${images.length > 1 ? `<div class="gallery-thumbs">${images.map((im, i) => `<button type="button" data-src="${im.url}" aria-label="Show photo ${i + 1}" ${i === 0 ? 'aria-current="true"' : ''}><img src="${im.url}" alt=""></button>`).join('')}</div>` : ''}`;
}

function render() {
  document.title = item.title + ' - Campus Lost & Found';
  root.innerHTML = `
    <div class="page-head"><a href="items.html" class="small">&larr; Back to listings</a>
      <div class="row" style="margin-top:10px">${typeTag(item.item_type)}${itemStatusBadge(item.status)}</div>
      <h1 style="margin-top:8px;overflow-wrap:anywhere">${esc(item.title)}</h1></div>
    <div class="detail">
      <div class="stack">
        <div>${gallery(item.images)}</div>
        <div class="card"><h3>Description</h3><div class="prose">${esc(item.description)}</div></div>
      </div>
      <div class="stack">
        <div class="card"><dl class="facts">
          <dt>Type</dt><dd>${item.item_type === 'LOST' ? 'Lost item' : 'Found item'}</dd>
          <dt>${item.item_type === 'LOST' ? 'Date lost' : 'Date found'}</dt><dd>${esc(fmtDate(item.item_date))}</dd>
          <dt>Location</dt><dd>${esc(item.location.location_name)}</dd>
          <dt>Category</dt><dd>${esc(item.category.category_name)}</dd>
          <dt>Reported</dt><dd>${esc(fmtDate(item.created_at))}</dd></dl></div>
        <div id="side" class="stack"><div class="skel" style="min-height:140px"></div></div>
      </div>
    </div>
    <section id="claims-section" class="section hidden"></section>`;
  root.querySelectorAll('.gallery-thumbs button').forEach((b) => b.addEventListener('click', () => {
    $('#main-img').src = b.dataset.src;
    root.querySelectorAll('.gallery-thumbs button').forEach((x) => x.removeAttribute('aria-current')); b.setAttribute('aria-current', 'true');
  }));
}

const accepting = () => item.item_type === 'FOUND' && ['ACTIVE', 'CLAIM_PENDING'].includes(item.status);
const closedNote = () => ({ CLAIMED: 'A claim for this item has been approved and the handover is being arranged.', RETURNED: 'This item has been returned to its owner.', CLOSED: 'This report is closed.' }[item.status] || '');

async function reload() { api.clearItemCache(); await load(); }

async function renderSide() {
  const side = $('#side'), cs = $('#claims-section');
  const next = encodeURIComponent('item.html?id=' + item.item_id);
  if (!user) {
    side.innerHTML = `<div class="card"><h3>${item.item_type === 'FOUND' ? 'Is this yours?' : 'Did you find this?'}</h3>
      <p class="muted">${item.item_type === 'FOUND' ? 'Log in to submit an ownership claim. Your evidence stays private.' : 'Log in to report that you found it.'}</p>
      <a class="btn btn-primary btn-block" href="login.html?next=${next}">Log in to continue</a>
      <p class="small muted center" style="margin:12px 0 0">No account? <a href="register.html">Create one</a></p></div>`;
    return;
  }
  const isAdmin = user.role === 'ADMIN';
  let claims = null; // an array when I am the finder (owner) or an admin
  try { claims = (await api.itemClaims(item.item_id)).claims; } catch (e) { if (e.status !== 403) throw e; }
  const isOwner = claims !== null && !isAdmin;

  if (claims !== null) {
    side.innerHTML = `<div class="card"><h3>${isAdmin ? 'Administrator view' : 'Your report'}</h3>
      <p class="muted small">${isAdmin ? 'You can see every claim and its private evidence.' : (item.item_type === 'FOUND' ? 'You found this item. Review each claim and approve only if the evidence matches the item you hold.' : 'You reported this item as lost.')}</p>
      <div class="row">${isOwner && item.status === 'ACTIVE' ? `<a class="btn btn-secondary btn-sm" href="report.html?edit=${item.item_id}">Edit report</a><button class="btn btn-secondary btn-sm" id="close-btn" type="button">Close report</button>` : ''}
      ${isAdmin ? '<a class="btn btn-secondary btn-sm" href="admin.html">Admin dashboard</a>' : ''}</div></div>`;
    const cb = $('#close-btn');
    if (cb) cb.addEventListener('click', async () => {
      const ok = await confirmBox({ title: 'Close this report?', text: 'It will no longer accept claims or edits. This cannot be undone.', confirmText: 'Close report', danger: true });
      if (!ok) return;
      busy(cb, async () => { try { await api.closeItem(item.item_id); toast('Report closed.', 'ok'); await reload(); } catch (e) { toast(e.message, 'error'); } });
    });
    if (item.item_type === 'FOUND') {
      cs.classList.remove('hidden');
      await attachHandovers(claims);
      cs.innerHTML = `<h2>Claims on this item <span class="muted" style="font-size:1rem">(${claims.length})</span></h2><div class="stack" id="claim-list"></div>`;
      const list = $('#claim-list');
      if (!claims.length) list.innerHTML = emptyState('No claims yet', 'When someone claims this item, their evidence will appear here for review.');
      claims.forEach((c) => list.appendChild(renderClaimCard(c, { me: user, item, handover: c._handover, link: true, onChange: reload })));
    }
    return;
  }

  // I am a regular user viewing someone else's report
  if (item.item_type === 'LOST') {
    side.innerHTML = `<div class="card"><h3>Did you find this?</h3><p class="muted">Report it as a found item so the owner can claim it through the portal.</p><a class="btn btn-primary btn-block" href="report.html?type=FOUND">Report a found item</a></div>`;
    return;
  }
  const mine = (await api.myClaims()).claims.find((c) => c.item_id === item.item_id);
  if (mine) {
    await attachHandovers([mine]);
    side.innerHTML = '<h3 style="margin:0">Your claim</h3>';
    side.appendChild(renderClaimCard(mine, { me: user, item, handover: mine._handover, link: true, onChange: reload }));
    return;
  }
  if (!accepting()) { side.innerHTML = `<div class="alert alert-info">${icon('info')}<div>${esc(closedNote() || 'This item is not accepting claims.')}</div></div>`; return; }
  side.innerHTML = `<form class="card" id="claim-form" novalidate><h3>Claim this item</h3>
    <p class="muted small">Describe something only the owner would know: contents, marks, serial number, lock-screen photo. Do not just repeat the public description.</p>
    <div class="field"><label for="evidence">Ownership evidence <span class="counter" id="ev-count">0 / 5000</span></label>
      <textarea id="evidence" class="input" maxlength="5000" required placeholder="e.g. There is a green sticker inside the cover and my name is written on page 1."></textarea></div>
    <div class="alert alert-info" style="margin-bottom:16px">${icon('lock')}<div>This is private. Only the finder and administrators can read it.</div></div>
    <div id="claim-error"></div>
    <button class="btn btn-primary btn-block" type="submit" id="claim-submit">Submit claim</button></form>`;
  const ta = $('#evidence');
  ta.addEventListener('input', () => { $('#ev-count').textContent = ta.value.length + ' / 5000'; });
  $('#claim-form').addEventListener('submit', (e) => {
    e.preventDefault();
    if (!ta.value.trim()) { ta.classList.add('invalid'); inlineError($('#claim-error'), 'Describe how you can prove this item is yours.'); return; }
    busy($('#claim-submit'), async () => {
      try { await api.submitClaim(item.item_id, ta.value.trim()); toast('Claim submitted. The finder has been notified.', 'ok'); await reload(); }
      catch (err) { inlineError($('#claim-error'), err.message); if (err.status === 409) await reload(); }
    });
  });
}

async function load() {
  root.innerHTML = `<div class="page-head"><div class="skel" style="min-height:90px"></div></div><div class="grid">${skeletons(1, 300)}</div>`;
  if (!id) { root.innerHTML = emptyState('Item not found', 'The link is missing an item number.', '<a class="btn btn-primary" href="items.html">Browse items</a>'); return; }
  try { item = (await api.item(id)).item; }
  catch (e) {
    if (e.status === 404) root.innerHTML = emptyState('Item not found', 'It may have been removed.', '<a class="btn btn-primary" href="items.html">Browse items</a>');
    else showError(root, e, load);
    return;
  }
  render();
  try { await renderSide(); } catch (e) { showError($('#side'), e, load); }
}
load();
