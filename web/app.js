const form = document.querySelector('#search-form');
const query = document.querySelector('#query');
const message = document.querySelector('#message');
const results = document.querySelector('#results');
const metrics = document.querySelector('#metrics');
const metricsContent = document.querySelector('#metrics-content');
const badge = document.querySelector('#cluster-badge');

const escape = value => String(value).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

async function refreshCluster() {
  try {
    const cluster = await fetch('/api/cluster').then(r => r.json());
    const nodesUp = cluster.processes.filter(p => p.kind === 'node' && p.state === 'running').length;
    const coordinatorsUp = cluster.processes.filter(p => p.kind === 'coordinator' && p.state === 'running').length;
    badge.innerHTML = cluster.leader
      ? `<strong>Leader ${escape(cluster.leader)}</strong> · epoch ${cluster.epoch}<br>${coordinatorsUp}/3 coordinators · ${nodesUp}/3 nodes<br>statistics v${cluster.stats_version}`
      : `<strong class="warn">No leader</strong><br>${coordinatorsUp}/3 coordinators · ${nodesUp}/3 nodes<br>Start the cluster or wait for the election.`;
  } catch {
    badge.textContent = 'Web server unreachable.';
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const value = query.value.trim();
  if (!value) return;
  message.textContent = 'Searching all available shards…';
  results.innerHTML = '';
  metrics.hidden = true;
  try {
    const response = await fetch('/api/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query: value, top_k: 10})});
    if (!response.ok) throw Error((await response.json()).detail || 'search failed');
    render(await response.json());
  } catch (error) {
    message.textContent = `The search could not be completed: ${error.message}`;
  }
});

function render(data) {
  message.textContent = `${data.results.length} result${data.results.length === 1 ? '' : 's'} · ${data.healthy_nodes}/${data.total_nodes} nodes answered · ${data.elapsed_ms} ms · served by ${data.coordinator_id}`;
  results.innerHTML = data.results.map(r => `<article class="result"><h2><a href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.title)}</a></h2><div class="url">${escape(r.url)}</div><p class="snippet">${escape(r.snippet)}</p><div class="meta">Cosine similarity: ${r.score.toFixed(4)} · ${escape(r.node_id)} · document ${r.document_id}</div></article>`).join('') || '<p class="message">No matching indexed documents were found.</p>';
  metrics.hidden = false;
  metricsContent.innerHTML = `<div class="metric-grid">
      <div class="metric"><strong>${escape(data.coordinator_id)}</strong>${escape(data.coordinator_role.toLowerCase())}, epoch ${data.epoch}</div>
      <div class="metric"><strong>v${data.stats_version}</strong>statistics version</div>
      <div class="metric"><strong>${data.healthy_nodes}/${data.total_nodes}</strong>nodes answered</div>
      <div class="metric"><strong>${data.candidate_count}</strong>candidates merged</div></div>
    <table class="nodes"><thead><tr><th>Node</th><th>Status</th><th>Latency</th><th>Hits</th></tr></thead><tbody>${data.node_status.map(n => `<tr><td>${escape(n.node_id)}</td><td class="${n.status === 'up' ? 'up' : 'unavailable'}">${escape(n.status)}</td><td>${n.status === 'unavailable' ? '—' : n.latency_ms + ' ms'}</td><td>${n.status === 'unavailable' ? '—' : n.candidate_count}</td></tr>`).join('')}</tbody></table>`;
}

refreshCluster();
setInterval(refreshCluster, 2000);

// A link such as /?q=raft+quorum runs the search straight away (handy for demos and screenshots).
const initialQuery = new URLSearchParams(location.search).get('q');
if (initialQuery) { query.value = initialQuery; form.requestSubmit(); }
