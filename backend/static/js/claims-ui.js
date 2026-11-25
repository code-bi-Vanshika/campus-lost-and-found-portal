// Claim display + actions shared by the item page, claim page, finder inbox and admin dashboard.
import { api } from './api.js';
import { icon } from './icons.js';
import { esc, fmtDate, fmtDateTime, toast, busy, askText, confirmBox, stageBadge, $, $$ } from './ui.js';

export async function mapLimit(list, limit, fn) {
  const out = new Array(list.length); let i = 0;
  await Promise.all(Array.from({ length: Math.min(limit, list.length) }, async () => {
    while (i < list.length) { const n = i++; out[n] = await fn(list[n], n); }
  }));
  return out;
}

// handover: object = recorded, null = checked and none, undefined = not checked
export function claimStage(c, handover) {
  if (c.status === 'REJECTED') return { key: 'rejected', tone: 'b-bad', label: c.finder_decision === 'REJECTED' ? 'Rejected by finder' : 'Rejected by administrator' };
  if (c.status === 'APPROVED') return handover ? { key: 'returned', tone: 'b-done', label: 'Item returned' } : { key: 'approved', tone: 'b-active', label: 'Approved - awaiting handover' };
  if (c.finder_decision === 'APPROVED') return { key: 'awaiting-admin', tone: 'b-info', label: 'Awaiting administrator' };
  return { key: 'awaiting-finder', tone: 'b-pending', label: 'Awaiting finder review' };
}

export function timeline(c, handover) {
  const f = c.finder_decision, a = c.admin_decision;
  const steps = [
    ['done', 'Submitted', fmtDate(c.claim_date)],
    [f === 'APPROVED' ? 'done' : f === 'REJECTED' ? 'bad' : c.status === 'PENDING' ? 'current' : '', f === 'REJECTED' ? 'Finder rejected' : 'Finder review', c.finder_decided_at ? fmtDate(c.finder_decided_at) : ''],
    [a === 'APPROVED' ? 'done' : a === 'REJECTED' ? 'bad' : f === 'APPROVED' && c.status === 'PENDING' ? 'current' : '', a === 'REJECTED' ? 'Admin rejected' : 'Admin decision', c.admin_decided_at ? fmtDate(c.admin_decided_at) : ''],
    [handover ? 'done' : c.status === 'APPROVED' ? 'current' : '', handover ? 'Item returned' : 'Handover', handover ? fmtDate(handover.handover_date) : '']
  ];
  return `<ol class="steps" aria-label="Claim progress">${steps.map(([cls, l, s]) => `<li class="${cls}">${esc(l)}<small>${esc(s)}</small></li>`).join('')}</ol>`;
}

const itemOpen = (item) => !item || !['RETURNED', 'CLOSED'].includes(item.status);

// ctx: { me, item?, handover?, showItem?, onChange? }
export function renderClaimCard(c, ctx) {
  const { me, item, handover, showItem, onChange } = ctx;
  const isAdmin = me.role === 'ADMIN', isClaimant = me.user_id === c.claimant_id;
  const isFinder = !isAdmin && !isClaimant; // the API only returns a claim to its claimant, the finder or an admin
  const stage = claimStage(c, handover);
  const open = itemOpen(item);
  // Another claim is already approved for this item: this one waits (it revives if that approval is cancelled).
  const onHold = !!item && item.status === 'CLAIMED' && c.status === 'PENDING';
  const acts = [];
  if (isFinder && open && c.status === 'PENDING' && c.finder_decision === 'PENDING')
    acts.push(['finder-approve', 'Approve claim', 'btn-primary'], ['finder-reject', 'Reject claim', 'btn-secondary']);
  if (isAdmin && open && c.status === 'PENDING' && c.finder_decision === 'APPROVED' && c.admin_decision === 'PENDING')
    acts.push(...(onHold ? [] : [['admin-approve', 'Approve claim', 'btn-primary']]), ['admin-reject', 'Reject claim', 'btn-secondary']);
  if (isAdmin && c.status === 'APPROVED' && handover === null)
    acts.push(['handover', 'Record handover', 'btn-primary'], ['cancel', 'Cancel approval', 'btn-secondary']);

  const el = document.createElement('article');
  el.className = 'claim-card' + (acts.length ? ' attn' : '');
  const title = showItem && (item || c.item_title)
    ? `<h3 style="font-family:var(--sans);font-size:1.05rem;margin:0"><a href="item.html?id=${c.item_id}">${esc(item ? item.title : c.item_title)}</a></h3>` : '';
  el.innerHTML = `
    <div class="row between"><div>${title}
      <div class="muted small">${isClaimant ? 'Your claim' : 'Claim by ' + esc(c.claimant_name || 'a claimant')} &middot; submitted ${esc(fmtDateTime(c.claim_date))}</div></div>
      <div>${stageBadge(stage)}</div></div>
    ${timeline(c, handover)}
    ${c.ownership_evidence != null ? `<div class="evidence"><div class="label">${icon('lock', 14)} ${isClaimant ? 'Your ownership evidence (private)' : 'Ownership evidence (private) - only the claimant, the finder and administrators can see this'}</div><div class="prose">${esc(c.ownership_evidence)}</div></div>` : ''}
    ${c.finder_remarks ? `<div class="remark ${c.finder_decision === 'REJECTED' ? 'bad' : ''}"><strong>Finder's note:</strong> ${esc(c.finder_remarks)}</div>` : ''}
    ${c.admin_remarks ? `<div class="remark ${c.admin_decision === 'REJECTED' ? 'bad' : ''}"><strong>Administrator's note:</strong> ${esc(c.admin_remarks)}</div>` : ''}
    ${handover ? `<div class="alert alert-ok">${icon('check')}<div>Handed over on ${esc(fmtDateTime(handover.handover_date))}.${handover.remarks ? ' ' + esc(handover.remarks) : ''}</div></div>` : ''}
    ${isClaimant && stage.key === 'approved' ? `<div class="alert alert-info">${icon('info')}<div>Your claim is fully approved. Contact the university lost &amp; found desk to collect your item.</div></div>` : ''}
    ${onHold ? `<div class="alert alert-warn">${icon('clock')}<div>On hold: another claim is already approved for this item. This claim stays pending and can be approved only if that approval is cancelled.</div></div>` : ''}
    ${acts.length ? `<div class="row">${acts.map(([k, l, cls]) => `<button type="button" class="btn ${cls} btn-sm" data-act="${k}">${l}</button>`).join('')}</div>` : ''}
    ${ctx.link ? `<div><a class="small" href="claim.html?id=${c.claim_id}">Open claim details ${icon('arrow', 14)}</a></div>` : ''}`;

  const run = (btn, fn) => busy(btn, async () => {
    try { await fn(); onChange && onChange(); }
    catch (e) { toast(e.message, 'error'); onChange && onChange(); }
  });
  const id = c.claim_id;
  const handlers = {
    'finder-approve': async (b) => { const t = await askText({ title: 'Approve this claim?', label: 'Note for the administrator', confirmText: 'Approve claim', help: 'Only approve if the evidence matches the item you are holding.' }); if (t === null) return; await run(b, async () => { await api.finderDecision(id, 'APPROVED', t); toast('Claim approved. It now goes to an administrator.', 'ok'); }); },
    'finder-reject': async (b) => { const t = await askText({ title: 'Reject this claim?', label: 'Reason (the claimant will see this)', required: true, confirmText: 'Reject claim', danger: true }); if (t === null) return; await run(b, async () => { await api.finderDecision(id, 'REJECTED', t); toast('Claim rejected.', 'ok'); }); },
    'admin-approve': async (b) => { const t = await askText({ title: 'Give final approval?', label: 'Note', confirmText: 'Approve claim', help: 'The item will be reserved for this claimant until handover.' }); if (t === null) return; await run(b, async () => { await api.adminDecision(id, 'APPROVED', t); toast('Final approval recorded.', 'ok'); }); },
    'admin-reject': async (b) => { const t = await askText({ title: 'Reject this claim?', label: 'Reason (the claimant will see this)', required: true, confirmText: 'Reject claim', danger: true }); if (t === null) return; await run(b, async () => { await api.adminDecision(id, 'REJECTED', t); toast('Claim rejected.', 'ok'); }); },
    'cancel': async (b) => { const t = await askText({ title: 'Cancel this approval?', label: 'Reason (shown to the claimant)', required: true, confirmText: 'Cancel approval', danger: true, help: 'Use this if the claimant does not collect the item. It cannot be done after handover.' }); if (t === null) return; await run(b, async () => { await api.cancelApproval(id, t); toast('Approval cancelled. The item is open again.', 'ok'); }); },
    'handover': async (b) => { const t = await askText({ title: 'Record handover', label: 'Remarks, e.g. ID checked at the admin office', confirmText: 'Record handover', help: 'This marks the item as returned and rejects any other pending claims.' }); if (t === null) return; await run(b, async () => { await api.recordHandover(id, t); toast('Handover recorded. Item marked as returned.', 'ok'); }); }
  };
  $$('[data-act]', el).forEach((b) => b.addEventListener('click', () => handlers[b.dataset.act](b)));
  return el;
}

// Reads every page of a queue endpoint (50 per page).
async function readAll(fetchPage) {
  const rows = [];
  for (let page = 1; page <= 100; page++) {
    const d = await fetchPage(page);
    rows.push(...d.claims);
    if (d.claims.length < 50) break;
  }
  return rows;
}
const itemOf = (c) => ({ item_id: c.item_id, title: c.item_title, status: c.item_status, item_date: c.item_date });

// Claims on the items I reported. state: 'pending' (awaiting my decision) or 'all'.
export async function loadFinderClaims(state = 'all') {
  const claims = await readAll((page) => api.finderQueue({ state, page, per_page: 50 }));
  claims.forEach((c) => { c._item = itemOf(c); });
  return claims;
}

// Admin: approved claims awaiting handover -> [{ claim, item }]
export async function loadAwaitingHandover() {
  const claims = await readAll((page) => api.handoverQueue({ state: 'pending', page, per_page: 50 }));
  return claims.map((claim) => ({ claim, item: itemOf(claim) }));
}
// Admin: completed handovers -> [{ claim, item, handover }]
export async function loadCompletedHandovers() {
  const claims = await readAll((page) => api.handoverQueue({ state: 'completed', page, per_page: 50 }));
  return claims.map((claim) => ({ claim, item: itemOf(claim), handover: claim.handover }));
}

// Attach c._handover (object or null) to approved claims so stages/actions are accurate.
export async function attachHandovers(claims) {
  await mapLimit(claims.filter((c) => c.status === 'APPROVED'), 5, async (c) => {
    try { c._handover = (await api.handover(c.claim_id)).handover; }
    catch (e) { if (e.status === 404) c._handover = null; else throw e; }
  });
  return claims;
}
