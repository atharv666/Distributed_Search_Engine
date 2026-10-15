'use strict';

const PROCS = ['C1', 'C2', 'C3', 'N1', 'N2', 'N3'];
const CAT_COLOR = {add: '#1e5ccb', election: '#d6336c', search: '#2f9e44', sync: '#f08c00', beacon: '#868e96'};
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const LABEL = {
  // beacons
  beacon_sent: 'sends beacon', beacon_received: 'receives beacon', beacon_reply_sent: 'acknowledges beacon',
  beacon_reply_received: 'receives beacon acknowledgement', beacon_failed: 'beacon unanswered (peer down)',
  // adding a document
  request_received: 'receives the add request', fetch_started: 'fetches the page', html_fetched: 'page downloaded',
  html_parsed: 'HTML parsed', text_received: 'receives pasted text', document_json_built: 'builds the document JSON',
  submitted_to_leader: 'sends the document to the leader', leader_replied: 'leader confirms', ingest_failed: 'could not build a document',
  leader_unreachable: 'leader unreachable',
  document_received: 'receives the document', doc_id_assigned: 'assigns the document ID', node_selected: 'picks the least-loaded node',
  add_document_sent: 'sends the document to a node', add_document_received: 'receives the document', document_indexed: 'indexes it (inverted index updated)',
  add_document_reply_sent: 'confirms indexing', add_document_reply_received: 'receives the indexing confirmation', add_document_failed: 'node unreachable',
  statistics_updated: 'computes the new global statistics (N, DF)', replicate_delta_sent: 'replicates the delta to a standby',
  replicate_delta_received: 'receives the replicated delta', statistics_replicated: 'applies the replicated delta',
  replicate_delta_reply_sent: 'confirms replication', replicate_delta_reply_received: 'receives replication confirmation', replicate_delta_failed: 'standby unreachable',
  replicated_to_standbys: 'standbys hold the new statistics', apply_statistics_sent: 'pushes the new statistics to a node',
  apply_statistics_received: 'receives the new statistics', statistics_applied: 'applies them and recomputes document norms',
  apply_statistics_reply_sent: 'confirms statistics', apply_statistics_reply_received: 'receives statistics confirmation', apply_statistics_failed: 'node unreachable',
  statistics_applied_on_nodes: 'nodes hold the new statistics', document_searchable: 'document is now searchable',
  // search
  search_started: 'starts a search', search_sent: 'sends the query to a node', search_received: 'receives the query', scored_locally: 'scores its shard (global IDF)',
  search_reply_sent: 'returns its local top-K', search_reply_received: 'receives local results', results_merged: 'merges the global top-K', search_failed: 'node unreachable',
  // failure detection and election
  leader_suspected: 'suspects the leader (no beacon)', suspect_report_sent: 'reports the suspected leader', suspect_report_received: 'receives the suspicion report',
  suspect_reply_sent: 'replies to the report', suspect_report_reply_received: 'receives the reply', suspect_report_failed: 'coordinator unreachable',
  verifying_leader: 'verifies the leader', ping_sent: 'pings the leader', ping_received: 'receives a ping', ping_reply_sent: 'answers the ping',
  ping_reply_received: 'receives the ping answer', ping_failed: 'ping unanswered', leader_alive_false_alarm: 'leader answered: false alarm',
  leader_confirmed_down: 'confirms the leader is down', election_started: 'starts an election', election_sent: 'sends ELECTION to a higher coordinator',
  election_received: 'receives ELECTION', election_ok_sent: 'replies OK (I outrank you)', election_reply_received: 'receives OK',
  election_failed: 'ELECTION unanswered (higher coordinator is down)', waiting_for_winner: 'waits for the winner to announce', winner_never_announced: 'winner never announced',
  won_election: 'wins: nobody higher answered', catch_up_started: 'catches up on missed statistics', catch_up_sent: 'requests missed deltas', catch_up_requested: 'receives the catch-up request',
  catch_up_reply_sent: 'sends the missed deltas', catch_up_reply_received: 'receives the missed deltas', catch_up_done: 'caught up',
  announce_sent: 'announces leadership', announce_received: 'receives the announcement', leader_accepted: 'accepts the new leader',
  announce_reply_sent: 'acknowledges the announcement', announce_reply_received: 'receives the acknowledgement', announce_failed: 'peer unreachable',
  announce_rejected_retrying: 'announcement rejected (older epoch), retries', became_leader: 'becomes the leader', stepped_down: 'steps down', coordinator_started: 'starts up',
  joined_as_standby: 'joins as standby',
};
const KEY_ADD = new Set(['request_received', 'fetch_started', 'html_fetched', 'html_parsed', 'text_received', 'document_json_built', 'submitted_to_leader',
  'document_received', 'doc_id_assigned', 'node_selected', 'add_document_sent', 'document_indexed', 'statistics_updated', 'replicate_delta_sent', 'statistics_replicated',
  'replicated_to_standbys', 'apply_statistics_sent', 'statistics_applied', 'statistics_applied_on_nodes', 'document_searchable', 'leader_replied', 'ingest_failed', 'leader_unreachable']);
const KEY_ELECTION = new Set(['leader_suspected', 'suspect_report_sent', 'suspect_report_received', 'verifying_leader', 'ping_sent', 'ping_failed', 'leader_alive_false_alarm',
  'leader_confirmed_down', 'election_started', 'election_sent', 'election_received', 'election_failed', 'election_ok_sent', 'waiting_for_winner', 'winner_never_announced',
  'won_election', 'catch_up_started', 'catch_up_done', 'announce_sent', 'announce_received', 'leader_accepted', 'stepped_down', 'became_leader', 'announce_rejected_retrying', 'joined_as_standby']);
const KEY_SEARCH = new Set(['search_started', 'search_sent', 'scored_locally', 'results_merged']);

const SAMPLES = [
  {title: 'Raft consensus primer', content: 'Raft elects a leader with randomized timeouts and replicates a log to followers, so a majority quorum can always agree on the same committed entries.'},
  {title: 'Gossip protocols overview', content: 'Gossip protocols spread membership and failure information epidemically, with every peer repeatedly sharing state with a few random neighbours until the whole cluster converges.'},
  {title: 'Consistent hashing notes', content: 'Consistent hashing places nodes and keys on a ring so that adding or removing a node only remaps a small fraction of the keys instead of reshuffling everything.'},
  {title: 'Lamport and vector clocks', content: 'Lamport clocks give a total order consistent with causality, while vector clocks additionally reveal which events are concurrent by comparing one counter per process.'},
  {title: 'Quorum reads and writes', content: 'With replication factor N, a write quorum W and a read quorum R guarantee that every read overlaps the latest write whenever R plus W is greater than N.'},
  {title: 'Bully algorithm walkthrough', content: 'In the bully algorithm the process with the highest identifier always wins an election, and a recovering high-priority process simply starts a new election to take over.'},
];

const S = {
  events: [], byId: new Map(), lastId: 0, cluster: null, selection: {type: 'recent'}, picks: [],
  filters: {add: true, election: true, search: true, sync: true, beacon: false}, replay: null, opsSignature: '', sampleIndex: 0, lastRenderedCount: -1, showVectors: false, showMerge: true, prev: null, sendByMsg: null, layout: null,
};

// ------------------------------------------------------------------------------------------------ helpers
const pretty = name => String(name).replace(/_/g, ' ');
const labelOf = name => LABEL[name] || pretty(name);
const ownCounter = e => (e.vector ? e.vector[e.process] ?? 0 : '');
const clock = t => new Date(t * 1000).toLocaleTimeString([], {hour12: false});
function compareVec(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let le = true, ge = true;
  keys.forEach(k => { const x = a[k] || 0, y = b[k] || 0; if (x > y) le = false; if (x < y) ge = false; });
  return le && ge ? 'equal' : le ? 'before' : ge ? 'after' : 'concurrent';
}
// A vector is always shown in the same fixed order, e.g. [0, 0, 1, 0, 0, 0] = [C1, C2, C3, N1, N2, N3].
const vecArr = v => `[${PROCS.map(p => (v && v[p]) || 0).join(', ')}]`;
function vecHtml(v, prev, own) {
  if (!v) return '';
  const cells = PROCS.map(p => {
    const value = v[p] || 0;
    const changed = value !== ((prev && prev[p]) || 0);
    return `<span class="vc${changed ? ' chg' : ''}${p === own ? ' own' : ''}">${value}</span>`;
  });
  return `<span class="vector">[${cells.join(', ')}]</span>`;
}
function indexEvents() {      // previous event of the same process, and the send event of every message
  const last = {};
  S.prev = new Map(); S.sendByMsg = new Map();
  for (const e of S.events) {
    if (!e.vector) continue;
    S.prev.set(e.id, last[e.process] || null);
    last[e.process] = e;
    if (e.kind === 'send') S.sendByMsg.set(e.msg_id, e);
  }
}
const prevVec = e => (S.prev && S.prev.get(e.id) ? S.prev.get(e.id).vector : null);
const maxVec = (a, b) => Object.fromEntries(PROCS.map(p => [p, Math.max((a && a[p]) || 0, (b && b[p]) || 0)]));
const RULE = {local: 'own +1', send: 'own +1, attach vector', receive: 'max(local, message), then own +1'};
function mergeLine(e) {        // the arithmetic of one receive event, on a single line
  const sent = S.sendByMsg && S.sendByMsg.get(e.msg_id);
  if (!sent) return '';
  const before = prevVec(e) || {};
  const merged = maxVec(before, sent.vector);
  return `local ${vecHtml(before)} <b>max</b> message from ${esc(sent.process)} ${vecHtml(sent.vector)} = ${vecHtml(merged)} <b>then +1 on ${esc(e.process)}</b> → ${vecHtml(e.vector, merged, e.process)}`;
}
function inspectHtml(e) {
  const before = prevVec(e) || {};
  let how;
  if (e.kind === 'receive') how = mergeLine(e) || "merge with the sender's vector, then own entry +1 (the send event is not in view)";
  else if (e.kind === 'send') how = `own entry +1, then the whole vector travels in the message <code>${esc(e.msg_id)}</code><br>before ${vecHtml(before)} → ${vecHtml(e.vector, before, e.process)}`;
  else how = `own entry +1<br>before ${vecHtml(before)} → ${vecHtml(e.vector, before, e.process)}`;
  return `<div class="inspect"><b>${esc(describe(e))}</b> <span class="muted">· ${esc(e.kind)} · ${esc(e.category)}${e.op ? ' · ' + esc(e.op) : ''} · ${clock(e.time)}</span><br>
    <span class="muted">vector</span> ${vecHtml(e.vector, before, e.process)}<br><span class="muted">rule: ${esc(RULE[e.kind] || '')}</span><br>${how}</div>`;
}

function describe(e) {
  const arrow = e.peer ? (e.kind === 'send' ? ` → ${e.peer}` : e.kind === 'receive' ? ` ← ${e.peer}` : ` (${e.peer})`) : '';
  return `${e.process} ${labelOf(e.name)}${arrow}`;
}
function detailText(e) {
  return Object.entries(e.details || {}).filter(([k]) => k !== 'preview')
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ');
}
async function post(url, body) {
  const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

// ------------------------------------------------------------------------------------------------ cluster panel
async function refreshCluster() {
  try {
    S.cluster = await fetch('/api/cluster').then(r => r.json());
    renderSummary();
    renderProcesses();
  } catch {
    $('#summary').innerHTML = '<span class="hint">Web server unreachable.</span>';
  }
}

function renderSummary() {
  const c = S.cluster;
  const up = c.processes.filter(p => p.state === 'running').length;
  $('#beat-interval').textContent = c.heartbeat_interval;
  $('#beat-timeout').textContent = c.beat_timeout;
  $('#summary').innerHTML = `
    <div class="stat"><b>${c.leader ? esc(c.leader) : '—'}</b><span>leader</span></div>
    <div class="stat"><b>${c.epoch}</b><span>epoch</span></div>
    <div class="stat"><b>v${c.stats_version}</b><span>statistics version</span></div>
    <div class="stat"><b>${up}/6</b><span>processes up</span></div>
    <div class="stat"><b>${c.heartbeat_interval}s / ${c.beat_timeout}s</b><span>beacon / timeout</span></div>`;
  const coordinatorsRunning = c.processes.some(p => p.kind === 'coordinator' && p.state === 'running');
  const banner = $('#banner');
  if (!c.leader && coordinatorsRunning) {
    banner.hidden = false;
    banner.textContent = 'No leader right now. An election is in progress; searches still work, but documents cannot be added until a leader is announced.';
  } else if (!coordinatorsRunning && !up) {
    banner.hidden = false;
    banner.textContent = 'The cluster is stopped. Press "Start all".';
  } else {
    banner.hidden = true;
  }
}

function processCard(p, c) {
  const isLeader = c.leader === p.id;
  const running = p.state === 'running';
  const role = running ? (p.role || '') : p.state;
  const chipClass = running ? p.role : 'stopped';
  let body = '';
  if (running) {
    body += p.kind === 'coordinator'
      ? `<div class="pline"><span>epoch <b>${p.epoch}</b></span><span>statistics <b>v${p.stats_version}</b></span><span>N <b>${p.total_docs}</b></span></div>
         <div class="pline"><span>docs per node <b>${Object.entries(p.node_counts).sort().map(([k, v]) => `${k}=${v}`).join(' ')}</b></span></div>`
      : `<div class="pline"><span>epoch <b>${p.epoch}</b></span><span>statistics <b>v${p.stats_version}</b></span><span>shard docs <b>${p.doc_count}</b></span></div>`;
    if (isLeader || p.role === 'LEADER') {
      const alive = Object.entries(p.node_alive || {}).sort().map(([id, ok]) => `<span class="${ok ? 'ok' : 'no'}">${id} ${ok ? '✔' : '✖'}</span>`).join(' ');
      body += `<div class="pline"><span>beacons sent <b>${p.beacons_sent}</b></span></div><div class="alive">node beacon replies: ${alive || '—'}</div>`;
    } else {
      const pct = Math.min(100, p.last_beat_age / p.beat_timeout * 100);
      const level = pct > 80 ? 'bad' : pct > 50 ? 'warn' : '';
      body += `<div class="pline"><span>beacons received <b>${p.beacons_received}</b></span><span>from <b>${esc(p.leader_id || '—')}</b></span></div>
        <div class="bar" title="time since last beacon"><i class="${level}" style="width:${pct}%"></i></div>
        <div class="alive">last beacon ${p.last_beat_age.toFixed(0)}s ago (suspects leader at ${p.beat_timeout}s)</div>`;
    }
    body += `<div class="vec" title="current vector clock, order [C1, C2, C3, N1, N2, N3]">vector ${vecHtml(p.clock, p.clock, p.id)}</div>`;
  } else {
    body += `<div class="pline">${p.state === 'starting' ? 'starting up…' : p.state === 'unresponsive' ? 'process is running but not answering' : 'not running'}</div>`;
  }
  const action = running || p.state === 'starting' || p.state === 'unresponsive' ? 'stop' : 'start';
  return `<article class="pcard ${isLeader ? 'leader' : ''} ${running ? '' : 'down'}">
    <header><span class="pname"><i class="dot ${p.state}"></i>${p.id}</span><span class="chip ${chipClass}">${esc(role)}</span></header>
    ${body}
    <footer><span class="alive">${p.kind}</span><button class="btn small ${action === 'stop' ? 'danger' : ''}" data-act="${action}" data-pid="${p.id}">${action === 'stop' ? 'Kill' : 'Start'}</button></footer>
  </article>`;
}
function renderProcesses() {
  const c = S.cluster;
  $('#process-grid').innerHTML = PROCS.map(id => c.processes.find(p => p.id === id)).filter(Boolean).map(p => processCard(p, c)).join('');
}

$('#process-grid').addEventListener('click', async event => {
  const button = event.target.closest('button[data-act]');
  if (!button) return;
  button.disabled = true;
  try { await post(`/api/admin/processes/${button.dataset.pid}/${button.dataset.act}`); } catch (error) { alert(error.message); }
  setTimeout(refreshCluster, 400);
});
$('#start-all').onclick = async () => { await post('/api/admin/start-all'); setTimeout(refreshCluster, 400); };
$('#stop-all').onclick = async () => { await post('/api/admin/stop-all'); setTimeout(refreshCluster, 400); };
$('#reset-data').onclick = async () => {
  if (!confirm('This stops every process, deletes documents added from this page and restores the original shards. Continue?')) return;
  try {
    const result = await post('/api/admin/reset');
    S.events = []; S.byId.clear(); S.lastId = 0; S.selection = {type: 'recent'}; S.picks = [];
    $('#add-results').innerHTML = '';
    $('#add-status').textContent = `Restored ${result.restored_documents} original documents. Press "Start all".`;
    renderAll();
  } catch (error) { alert(error.message); }
  refreshCluster();
};

// ------------------------------------------------------------------------------------------------ add documents
function setBusy(busy) { ['#add-urls', '#add-text', '#add-samples'].forEach(id => { $(id).disabled = busy; }); }

async function submitDocuments(payload, count) {
  setBusy(true);
  $('#add-status').textContent = `Processing ${count} document${count > 1 ? 's' : ''} at the same time…`;
  try {
    const data = await post('/api/admin/documents', payload);
    $('#add-results').innerHTML = data.results.map(r => `<div class="addrow" data-op="${esc(r.op)}">
        ${r.ok ? `<span class="ok">✔ document ${r.doc_id} → ${esc(r.node_id)}</span> · statistics v${r.version} · via ${esc(r.coordinator_id)} (epoch ${r.epoch})`
               : `<span class="fail">✖ ${esc(r.stage === 'parse' ? 'could not build a document' : 'could not index')}</span>`}
        <small>${esc(r.title || r.source)}${r.ok ? '' : ' — ' + esc(r.error)}</small></div>`).join('');
    $('#add-status').textContent = 'Done. Click a result to see its lifecycle and timeline.';
    S.selection = {type: 'op', op: data.results[0].op};
    S.opsSignature = '';
    setTimeout(pollEvents, 700);
  } catch (error) {
    $('#add-status').textContent = `Failed: ${error.message}`;
  } finally {
    setBusy(false);
  }
}
$('#add-urls').onclick = () => {
  const urls = $('#url-input').value.split('\n').map(s => s.trim()).filter(Boolean);
  if (urls.length) submitDocuments({urls}, urls.length);
};
$('#add-text').onclick = () => {
  const content = $('#text-content').value.trim();
  if (content) submitDocuments({texts: [{title: $('#text-title').value.trim(), content}]}, 1);
};
$('#add-samples').onclick = () => {
  const pick = [SAMPLES[S.sampleIndex % SAMPLES.length], SAMPLES[(S.sampleIndex + 1) % SAMPLES.length]];
  S.sampleIndex += 2;
  submitDocuments({texts: pick}, 2);
};
$('#add-results').addEventListener('click', event => {
  const row = event.target.closest('.addrow');
  if (row) { S.selection = {type: 'op', op: row.dataset.op}; S.opsSignature = ''; renderAll(); }
});

// ------------------------------------------------------------------------------------------------ events
async function pollEvents() {
  try {
    const data = await fetch(`/api/events?since=${S.lastId}`).then(r => r.json());
    if (!data.events.length) return;
    data.events.forEach(e => { S.events.push(e); S.byId.set(e.id, e); });
    S.lastId = data.last_id;
    if (S.events.length > 25000) S.events.splice(0, S.events.length - 20000);
    if (!S.replay) renderAll();
  } catch { /* the web server may be restarting */ }
}

function opsList() {
  const ops = new Map();
  for (const e of S.events) {
    if (!e.op) continue;
    let o = ops.get(e.op);
    if (!o) { o = {op: e.op, first: e.time, last: e.time, category: e.op.startsWith('failover') || e.op.startsWith('election') ? 'election' : e.category, title: '', query: ''}; ops.set(e.op, o); }
    o.last = Math.max(o.last, e.time);
    o.first = Math.min(o.first, e.time);
    if (e.details) { o.title = o.title || e.details.title || e.details.source || ''; o.query = o.query || e.details.query || ''; }
  }
  return [...ops.values()].sort((a, b) => b.last - a.last);
}
function opText(o) {
  if (o.op.startsWith('doc-')) return `Add · ${o.title || o.op}`;
  if (o.op.startsWith('failover-')) return `Failover · leader of epoch ${o.op.split('-e')[1]} went silent`;
  if (o.op.startsWith('election-')) return `Election · started by ${o.op.split('-')[1]}`;
  if (o.op.startsWith('search-')) return `Search · "${o.query}"`;
  if (o.op.startsWith('sync-')) return `Sync · ${o.op.slice(5)} catching up`;
  return o.op;
}
const opLabel = o => `${clock(o.first)}  ${opText(o)}`;
function renderOpSelect(ops) {
  const signature = ops.map(o => o.op).join('|') + JSON.stringify(S.selection);
  if (signature === S.opsSignature) return;
  S.opsSignature = signature;
  const value = S.selection.type === 'op' ? `op:${S.selection.op}` : S.selection.type === 'ops' ? 'pair' : S.selection.type;
  $('#op-select').innerHTML = `<option value="recent">Recent activity (no beacons)</option><option value="beacons">Beacons, last 40 s</option><option value="pair">Last two adds side by side</option>`
    + ops.slice(0, 40).map(o => `<option value="op:${esc(o.op)}">${esc(opLabel(o))}</option>`).join('');
  $('#op-select').value = value;
}
$('#op-select').onchange = event => {
  const v = event.target.value;
  S.picks = [];
  if (v === 'pair') { if (!selectPair()) { $('#replay-caption').textContent = 'Add two documents at once first ("Add 2 sample texts at once").'; } }
  else S.selection = v.startsWith('op:') ? {type: 'op', op: v.slice(3)} : {type: v};
  S.opsSignature = ''; stopReplay(); renderAll();
};
document.querySelectorAll('[data-quick]').forEach(button => button.onclick = () => {
  const kind = button.dataset.quick;
  if (kind === 'beacon') S.selection = {type: 'beacons'};
  else if (kind === 'pair') {
    if (!selectPair()) { $('#replay-caption').textContent = 'Add two documents at once first ("Add 2 sample texts at once").'; return; }
    stopReplay(); renderAll(); return;
  } else {
    const found = opsList().find(o => o.category === kind);
    if (!found) { $('#replay-caption').textContent = `No ${kind} operation has been recorded yet.`; return; }
    S.selection = {type: 'op', op: found.op};
  }
  S.picks = []; S.opsSignature = ''; stopReplay(); renderAll();
});
document.querySelectorAll('#filters input').forEach(box => box.onchange = () => { S.filters[box.dataset.cat] = box.checked; renderAll(); });

// Two documents added at the same moment: show both operations and pre-select their indexing events to compare.
function selectPair() {
  const indexed = S.events.filter(e => e.name === 'document_indexed');
  const ops = [...new Set(indexed.map(e => e.op).reverse())].slice(0, 2);
  if (ops.length < 2) return false;
  S.selection = {type: 'ops', ops};
  S.picks = ops.map(op => indexed.filter(e => e.op === op).pop().id);
  S.opsSignature = '';
  return true;
}

function viewEvents() {
  const sel = S.selection;
  let list;
  if (sel.type === 'op') list = S.events.filter(e => e.op === sel.op);
  else if (sel.type === 'ops') list = S.events.filter(e => sel.ops.includes(e.op));
  else if (sel.type === 'beacons') { const cutoff = Date.now() / 1000 - 40; list = S.events.filter(e => e.category === 'beacon' && e.time > cutoff).slice(-150); }
  else list = S.events.filter(e => e.vector && e.category !== 'beacon' && S.filters[e.category]).slice(-160);
  return list;
}

// ------------------------------------------------------------------------------------------------ lifecycle panel
function renderLifecycle(ops) {
  const box = $('#lifecycle');
  // With no operation chosen, follow the most recent one so the panel is never empty.
  const op = S.selection.type === 'op' ? S.selection.op : (ops.find(o => o.category !== 'beacon') || {}).op;
  if (!op) {
    $('#lifecycle-title').textContent = 'Lifecycle';
    box.innerHTML = '<p class="hint">Add a document, trigger a search or kill the leader. The steps appear here with their vector timestamps.</p>';
    return;
  }
  const all = S.events.filter(e => e.op === op);
  const keySet = op.startsWith('doc-') || op.startsWith('sync-') ? KEY_ADD : op.startsWith('search-') ? KEY_SEARCH : KEY_ELECTION;
  const observer = all.filter(e => e.kind === 'observer' && e.name !== 'leader_replied').sort((a, b) => a.time - b.time);
  const finalObserver = all.filter(e => e.name === 'leader_replied');
  const depth = layout(all.filter(e => e.vector));
  const seen = new Set();
  const clocked = all.filter(e => e.vector && keySet.has(e.name)).sort((a, b) => (depth.get(a.id) - depth.get(b.id)) || (a.time - b.time))
    .filter(e => { const key = `${e.process}|${e.name}|${e.peer}`; if (seen.has(key)) return false; seen.add(key); return true; });
  const rows = [...observer, ...clocked, ...finalObserver];
  if (!rows.length) { box.innerHTML = '<p class="hint">Waiting for events…</p>'; return; }
  const origin = Math.min(...rows.map(e => e.time));
  $('#lifecycle-title').textContent = `Lifecycle · ${opText(opsList().find(o => o.op === op) || {op})}`;

  const built2 = all.find(e => e.name === 'document_json_built');
  const assigned = all.find(e => e.name === 'doc_id_assigned');
  let json = '';
  if (built2 && built2.details) {
    const d = built2.details;
    json = `<pre class="json">${esc(JSON.stringify({document_id: assigned ? assigned.details.doc_id : '(assigned by the leader)', title: d.title, url: d.url, source: 'admin',
      content_length: d.content_length, content: (d.preview || '') + (d.content_length > (d.preview || '').length ? '…' : '')}, null, 2))}</pre>`;
  }
  box.innerHTML = rows.map(e => {
    const where = e.process === 'web' ? 'web' : e.process;
    const cls = where === 'web' ? 'web' : where[0];
    return `<div class="step"><span class="t">+${(e.time - origin).toFixed(2)}s</span><span class="where ${cls}">${esc(where)}</span>
      <span class="what"><b>${esc(labelOf(e.name))}</b>${e.peer ? ` <span class="meta" style="display:inline">${e.kind === 'send' ? '→' : '←'} ${esc(e.peer)}</span>` : ''}
      ${detailText(e) ? `<span class="meta">${esc(detailText(e))}</span>` : ''}
      ${e.vector ? `<span class="vec">${vecHtml(e.vector, prevVec(e), e.process)}</span>` : '<span class="meta">outside the cluster: no vector clock</span>'}</span></div>`;
  }).join('') + json;
}

// ------------------------------------------------------------------------------------------------ timeline
function layout(events) {
  const byProcess = {}, sendByMessage = new Map(), depth = new Map();
  events.forEach(e => { (byProcess[e.process] ||= []).push(e); if (e.kind === 'send') sendByMessage.set(e.msg_id, e); });
  Object.values(byProcess).forEach(list => list.sort((a, b) => a.seq - b.seq));
  let changed = true, guard = 0;
  while (changed && guard++ < events.length + 5) {
    changed = false;
    for (const list of Object.values(byProcess)) {
      let previous = 0;
      for (const e of list) {
        let d = previous + 1;
        if (e.kind === 'receive') { const s = sendByMessage.get(e.msg_id); if (s && depth.has(s.id)) d = Math.max(d, depth.get(s.id) + 1); }
        if (depth.get(e.id) !== d) { depth.set(e.id, d); changed = true; }
        previous = depth.get(e.id);
      }
    }
  }
  return depth;
}

function renderTimeline(clocked) {
  const host = $('#timeline');
  if (!clocked.length) { host.innerHTML = '<div class="empty">No clocked events for this selection yet.</div>'; S.layout = null; return; }
  const depth = layout(clocked);
  const maxDepth = Math.max(...depth.values());
  const compact = e => PROCS.map(p => e.vector[p] || 0).join(',');
  const dx = S.showVectors ? Math.max(70, Math.max(...clocked.map(e => compact(e).length + 2)) * 5.6 + 12) : 42;
  const left = 58, laneHeight = S.showVectors ? 66 : 58, top = 14;
  // A single operation shows only the processes that took part; broader views keep all six lanes.
  const lanes = S.selection.type === 'op' || S.selection.type === 'ops' ? PROCS.filter(p => clocked.some(e => e.process === p)) : PROCS;
  const width = left + maxDepth * dx + 30, height = top + lanes.length * laneHeight + 8;
  const laneY = p => top + lanes.indexOf(p) * laneHeight + laneHeight / 2;
  const x = e => left + (depth.get(e.id) - 0.5) * dx;
  const sends = new Map(clocked.filter(e => e.kind === 'send').map(e => [e.msg_id, e]));
  const usedCategories = [...new Set(clocked.map(e => e.category))];
  let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><defs>${usedCategories.map(c =>
    `<marker id="ah-${c}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${CAT_COLOR[c] || '#555'}"/></marker>`).join('')}</defs>`;
  lanes.forEach((p, i) => {
    const y = top + i * laneHeight;
    if (i % 2 === 0) svg += `<rect class="lane-band" x="0" y="${y}" width="${width}" height="${laneHeight}"/>`;
    svg += `<line class="lane-line" x1="${left - 8}" y1="${laneY(p)}" x2="${width - 8}" y2="${laneY(p)}"/><text class="lane-label" x="12" y="${laneY(p) + 4}">${p}</text>`;
  });
  clocked.forEach(e => {
    if (e.kind !== 'receive') return;
    const s = sends.get(e.msg_id);
    if (!s || !depth.has(s.id)) return;
    const color = CAT_COLOR[e.category] || '#555';
    svg += `<line class="arrow" data-depth="${depth.get(e.id)}" x1="${x(s)}" y1="${laneY(s.process)}" x2="${x(e)}" y2="${laneY(e.process)}" stroke="${color}" stroke-width="1.6"
      ${e.category === 'beacon' ? 'stroke-dasharray="4 3"' : ''} marker-end="url(#ah-${e.category})"/>`;
  });
  clocked.forEach(e => {
    const color = CAT_COLOR[e.category] || '#555', cx = x(e), cy = laneY(e.process);
    const picked = S.picks.includes(e.id) ? 'picked' : '';
    let shape;
    if (e.kind === 'send') shape = `<circle class="${picked}" cx="${cx}" cy="${cy}" r="6" fill="${color}" stroke="${color}" stroke-width="2"/>`;
    else if (e.kind === 'receive') shape = `<circle class="${picked}" cx="${cx}" cy="${cy}" r="6" fill="#fff" stroke="${color}" stroke-width="2.2"/>`;
    else shape = `<rect class="${picked}" x="${cx - 5}" y="${cy - 5}" width="10" height="10" transform="rotate(45 ${cx} ${cy})" fill="${color}" stroke="${color}" stroke-width="2"/>`;
    let label = `<text class="cnt" x="${cx}" y="${cy + 20}" text-anchor="middle">${ownCounter(e)}</text>`;
    if (S.showVectors) {
      const before = prevVec(e) || {};
      const cells = PROCS.map(p => `<tspan class="${(e.vector[p] || 0) !== (before[p] || 0) ? 'chg' : ''}${p === e.process ? ' own' : ''}">${e.vector[p] || 0}</tspan>`).join(',');
      label = `<text class="vtext" x="${cx}" y="${cy + 21}" text-anchor="middle">[${cells}]</text>`;
    }
    svg += `<g class="ev" data-id="${e.id}" data-depth="${depth.get(e.id)}">${shape}${label}</g>`;
  });
  svg += '</svg>';
  host.innerHTML = svg;
  S.layout = {depth, maxDepth, clocked};
}

function renderCompare() {
  const box = $('#compare');
  const picked = S.picks.map(id => S.byId.get(id)).filter(Boolean);
  box.hidden = !picked.length;
  if (!picked.length) { box.innerHTML = ''; return; }
  let html = picked.map(inspectHtml).join('');
  if (picked.length === 2) {
    const relation = compareVec(picked[0].vector, picked[1].vector);
    const text = {before: 'happened before', after: 'happened after', equal: 'is the same moment as', concurrent: 'is concurrent with (neither caused the other)'}[relation];
    html += `<div class="relation">${esc(picked[0].process)}#${ownCounter(picked[0])} <span class="verdict ${relation}">${text}</span> ${esc(picked[1].process)}#${ownCounter(picked[1])}
      <span class="muted">${relation === 'concurrent' ? '(some entry is larger in each vector)' : relation === 'equal' ? '' : '(every entry of the earlier vector is ≤ the later one)'}</span></div>`;
  }
  box.innerHTML = `<button class="btn small" id="clear-picks">Clear selection</button>${html}`;
  $('#clear-picks').onclick = () => { S.picks = []; togglePick(-1); };
}
function togglePick(id) {
  if (id !== -1) S.picks = S.picks.includes(id) ? S.picks.filter(p => p !== id) : [...S.picks, id].slice(-2);
  document.querySelectorAll('#timeline .ev').forEach(g => g.firstElementChild.classList.toggle('picked', S.picks.includes(Number(g.dataset.id))));
  document.querySelectorAll('#vtrace .vrow').forEach(r => r.classList.toggle('picked', S.picks.includes(Number(r.dataset.id))));
  renderCompare();
}
const timeline = $('#timeline');
timeline.addEventListener('click', event => {
  const target = event.target.closest('.ev');
  if (target) togglePick(Number(target.dataset.id));
});
$('#vtrace').addEventListener('click', event => {
  const row = event.target.closest('.vrow');
  if (row) togglePick(Number(row.dataset.id));
});
const tooltip = $('#tooltip');
timeline.addEventListener('mousemove', event => {
  const target = event.target.closest('.ev');
  if (!target) { tooltip.hidden = true; return; }
  const e = S.byId.get(Number(target.dataset.id));
  if (!e) return;
  tooltip.innerHTML = `<b>${esc(describe(e))}</b><br>${esc(e.kind)} · ${esc(e.category)}${e.op ? ' · ' + esc(e.op) : ''} · ${clock(e.time)}<br>
    ${vecHtml(e.vector, prevVec(e), e.process)}${e.msg_id ? '<br>message ' + esc(e.msg_id) + (e.peer ? (e.kind === 'send' ? ' → ' : ' ← ') + esc(e.peer) : '') : ''}${detailText(e) ? '<br>' + esc(detailText(e)) : ''}`;
  tooltip.hidden = false;
  tooltip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - 440)}px`;
  tooltip.style.top = `${event.clientY + 16}px`;
});
timeline.addEventListener('mouseleave', () => { tooltip.hidden = true; });

// ------------------------------------------------------------------------------------------------ vector trace table
function renderTrace(clocked) {
  const host = $('#vtrace');
  if (!clocked.length) { host.innerHTML = '<div class="empty">No clocked events for this selection yet.</div>'; return; }
  const depth = S.layout ? S.layout.depth : layout(clocked);
  const rows = [...clocked].sort((a, b) => (depth.get(a.id) - depth.get(b.id)) || (PROCS.indexOf(a.process) - PROCS.indexOf(b.process)));
  const glyph = {send: '→ send', receive: '← receive', local: '● local'};
  const body = rows.map(e => {
    const message = e.kind === 'local' ? '' : `${e.kind === 'send' ? '→' : '←'} ${esc(e.peer)}<br><span class="muted">${esc(e.msg_id)}</span>`;
    let html = `<tr class="vrow ${S.picks.includes(e.id) ? 'picked' : ''}" data-id="${e.id}" data-depth="${depth.get(e.id)}">
      <td class="num">${depth.get(e.id)}</td><td><b>${esc(e.process)}</b></td>
      <td><span class="cat" style="color:${CAT_COLOR[e.category] || '#555'}">${glyph[e.kind]}</span> ${esc(labelOf(e.name))}</td>
      <td class="msg">${message}</td><td class="rule">${esc(RULE[e.kind] || '')}</td>
      <td class="vcol">${vecHtml(e.vector, prevVec(e), e.process)}</td><td class="det">${esc(detailText(e))}</td></tr>`;
    if (S.showMerge && e.kind === 'receive') {
      const line = mergeLine(e);
      if (line) html += `<tr class="mergerow" data-depth="${depth.get(e.id)}"><td></td><td colspan="6">${line}</td></tr>`;
    }
    return html;
  }).join('');
  host.innerHTML = `<table class="vtable"><thead><tr><th>Step</th><th>Process</th><th>Event</th><th>Message</th><th>Rule</th>
    <th>Vector clock <span class="order">[${PROCS.join(', ')}]</span></th><th>Details</th></tr></thead><tbody>${body}</tbody></table>`;
}
$('#show-vectors').onchange = event => { S.showVectors = event.target.checked; stopReplay(); renderAll(); };
$('#show-merge').onchange = event => { S.showMerge = event.target.checked; renderAll(); };

// ------------------------------------------------------------------------------------------------ replay animation
function stopReplay() {
  if (S.replay) { clearInterval(S.replay); S.replay = null; }
  document.querySelectorAll('#timeline [data-depth], #vtrace [data-depth]').forEach(el => el.classList.remove('dim'));
  $('#replay').textContent = '▶ Replay';
}
function startReplay() {
  if (S.replay) { stopReplay(); renderAll(); return; }
  if (!S.layout) return;
  const {depth, maxDepth, clocked} = S.layout;
  const speed = Number($('#replay-speed').value);
  let step = 0;
  $('#replay').textContent = '■ Stop';
  const apply = () => {
    document.querySelectorAll('#timeline [data-depth], #vtrace [data-depth]').forEach(el => el.classList.toggle('dim', Number(el.dataset.depth) > step));
    const now = clocked.filter(e => depth.get(e.id) === step);
    $('#replay-caption').innerHTML = step === 0 ? 'Replaying…' : `<b>Step ${step}/${maxDepth}</b>: ` + now.map(e => `${esc(describe(e))} ${vecHtml(e.vector, prevVec(e), e.process)}`).join(' &nbsp;|&nbsp; ');
  };
  apply();
  S.replay = setInterval(() => {
    step += 1;
    apply();
    if (step >= maxDepth + 1) { stopReplay(); $('#replay-caption').textContent = 'Replay finished. Click any two events to compare their vector clocks.'; renderAll(); }
  }, speed);
}
$('#replay').onclick = startReplay;

// ------------------------------------------------------------------------------------------------ event log
function renderLog() {
  const rows = S.events.filter(e => e.kind !== 'observer' && S.filters[e.category]).slice(-120).reverse();
  const glyph = {send: '→', receive: '←', local: '●'};
  $('#event-log').innerHTML = rows.map(e => `<div class="logrow"><span>${clock(e.time)}</span><span>${esc(e.process)}</span><span title="${esc(e.kind)}">${glyph[e.kind] || '◇'}</span>
    <span><span class="cat" style="color:${CAT_COLOR[e.category] || '#555'}">${esc(labelOf(e.name))}</span>${e.peer ? ' ' + esc(e.peer) : ''}</span><span>#${ownCounter(e)}</span><span>${vecHtml(e.vector, prevVec(e), e.process)}</span></div>`).join('')
    || '<div class="empty">No events yet. Start the cluster.</div>';
}

// ------------------------------------------------------------------------------------------------ main render
// admin.html#add, #election, #search or #beacons opens the latest operation of that kind.
// Optional extra words: #add,vectors shows full vectors on the dots; #add,inspect pre-selects a message to inspect.
const hashWords = location.hash.slice(1).split(',').filter(Boolean);
S.pendingQuick = hashWords[0] === 'recent' ? '' : (hashWords[0] || '');
S.pendingInspect = hashWords.includes('inspect');
S.pendingConcurrent = hashWords.includes('concurrent');   // pre-select one indexing event of each of the two latest adds
if (hashWords.includes('full')) document.body.classList.add('full');
const focusWord = hashWords.find(word => word.startsWith('focus='));
if (focusWord) {                                           // show only the named panels (a+b); handy for screenshots and for presenting
  const targets = focusWord.slice(6).split('+').map(id => document.getElementById(id)).filter(Boolean);
  if (targets.length) {
    document.body.classList.add('focus');
    const keep = new Set();
    targets.forEach(target => { for (let node = target; node && node !== document.body; node = node.parentElement) keep.add(node); });
    keep.forEach(node => {
      if (node.parentElement && node.parentElement !== document.body) {
        [...node.parentElement.children].forEach(child => { if (!keep.has(child)) child.classList.add('hidden-by-focus'); });
      }
    });
  }
}
S.showVectors = hashWords.includes('vectors');
$('#show-vectors').checked = S.showVectors;
function applyPendingQuick() {
  if (!S.pendingQuick) return;
  if (S.pendingQuick === 'beacons') S.selection = {type: 'beacons'};
  else {
    const found = opsList().find(o => o.category === S.pendingQuick);
    if (!found) return;
    S.selection = {type: 'op', op: found.op};
  }
  S.pendingQuick = '';
  S.opsSignature = '';
}

function renderAll() {
  applyPendingQuick();
  indexEvents();
  const ops = opsList();
  renderOpSelect(ops);
  const events = viewEvents();
  renderLifecycle(ops);
  const clocked = events.filter(e => e.vector);
  if (S.pendingInspect && !S.pendingQuick && clocked.length > 1) {
    const received = [...clocked].reverse().find(e => e.kind === 'receive' && S.sendByMsg.get(e.msg_id)
      && clocked.some(x => x.id === S.sendByMsg.get(e.msg_id).id));
    if (received) { S.picks = [S.sendByMsg.get(received.msg_id).id, received.id]; S.pendingInspect = false; }
  }
  if (S.pendingConcurrent && selectPair()) { S.pendingConcurrent = false; return renderAll(); }
  renderTimeline(clocked);
  renderTrace(clocked);
  renderCompare();
  renderLog();
  document.querySelectorAll('.addrow').forEach(row => row.classList.toggle('selected', S.selection.type === 'op' && row.dataset.op === S.selection.op));
}

refreshCluster();
pollEvents();
renderAll();
setInterval(refreshCluster, 1000);
setInterval(pollEvents, 800);
