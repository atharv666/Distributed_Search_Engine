const form=document.querySelector('#search-form'),query=document.querySelector('#query'),message=document.querySelector('#message'),results=document.querySelector('#results'),metrics=document.querySelector('#metrics'),metricsContent=document.querySelector('#metrics-content'),controls=document.querySelector('#node-controls');
const escape=value=>String(value).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const display=value=>value===undefined||value===null||value===''?'—':escape(value);
const consistency=value=>['consistent','inconsistent','unverified'].includes(value)?value:'unverified';

async function refreshNodes(){
  const nodes=await fetch('/api/nodes').then(r=>r.json());
  controls.innerHTML=nodes.map(n=>`<div class="node-card"><div><div class="node-name">${escape(n.node_id)}</div><span class="node-state ${n.state==='running'?'running':''}">${escape(n.state)}</span></div><button class="toggle ${n.state==='running'?'stop':''}" data-node="${escape(n.node_id)}" data-action="${n.state==='running'?'stop':'start'}">${n.state==='running'?'Stop':'Start'}</button></div>`).join('');
  document.querySelectorAll('.toggle').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    await fetch(`/api/nodes/${encodeURIComponent(button.dataset.node)}/${button.dataset.action}`,{method:'POST'});
    setTimeout(refreshNodes,700);
  });
}

form.addEventListener('submit',async e=>{
  e.preventDefault();
  const value=query.value.trim();
  if(!value)return;
  message.textContent='Searching all available shards…';
  results.innerHTML='';
  metrics.hidden=true;
  try{
    const response=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:value,top_k:10})});
    if(!response.ok)throw Error();
    render(await response.json());
  }catch{
    message.textContent='The coordinator could not complete the search. Start one or more nodes and try again.';
  }
});

function renderNode(node){
  const rpc=node.rpc_state??(node.status==='up'?'responding':'unavailable');
  const index=consistency(node.index_consistency),generation=node.generation_consistency??'unverified',overall=consistency(node.consistency);
  const acceptance=node.results_accepted===true?'accepted':node.results_accepted===false?'excluded':'unknown';
  const errors=[...new Set([node.consistency_error,node.error].filter(Boolean))];
  return `<article class="query-node"><div class="query-node-heading"><strong>${display(node.node_id)}</strong><span class="${rpc==='responding'?'up':'unavailable'}">${escape(rpc)}</span></div><div class="${overall}">Consistency: ${escape(overall)} · results ${acceptance}</div><div class="node-facts">Index: ${escape(index)} · generation: ${escape(generation)}<br>Latency: ${display(node.latency_ms)}${node.latency_ms!=null?' ms':''} · candidates: ${display(node.candidate_count)}<br>Version: <code>${display(node.statistics_version)}</code></div>${errors.map(error=>`<p class="diagnostic-error">${escape(error)}</p>`).join('')}<details class="node-details"><summary>Index fingerprints</summary><dl><dt>Loaded index</dt><dd>${display(node.index_hash)}</dd><dt>Node expected</dt><dd>${display(node.expected_index_hash)}</dd><dt>Authority expected</dt><dd>${display(node.authoritative_index_hash)}</dd><dt>Candidates merged</dt><dd>${display(node.merged_candidate_count)}</dd></dl></details></article>`;
}

function renderTrace(data){
  const trace=Array.isArray(data.logical_trace)?data.logical_trace:[];
  return `<details class="logical-trace"><summary>Lamport trace (${trace.length} events)</summary><p class="trace-request">Request: <code>${display(data.request_id)}</code></p><p class="trace-note">Logical timestamps preserve causal order; comparing them alone does not prove causality.</p>${trace.length?`<ol>${trace.map(event=>`<li><strong>${display(event.logical_timestamp)}</strong><span>${display(event.process_id??event.node_id)}<br>${display(event.event)}</span></li>`).join('')}</ol>`:'<p class="trace-note">No logical trace was returned.</p>'}</details>`;
}

function render(data){
  const items=Array.isArray(data.results)?data.results:[],nodes=Array.isArray(data.node_status)?data.node_status:[];
  const healthy=data.healthy_nodes??0,total=data.total_nodes??nodes.length,eligible=data.eligible_nodes??healthy;
  message.textContent=`${items.length} result${items.length===1?'':'s'} · ${eligible}/${total} nodes eligible · ${healthy}/${total} responding · ${data.elapsed_ms??'—'} ms`;
  results.innerHTML=items.map(r=>`<article class="result"><h2><a href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.title)}</a></h2><div class="url">${escape(r.url)}</div><p class="snippet">${escape(r.snippet)}</p><div class="meta">Cosine similarity: ${Number.isFinite(r.score)?r.score.toFixed(4):'—'} · ${escape(r.node_id)}</div></article>`).join('')||'<p class="message">No matching indexed documents were found.</p>';
  metrics.hidden=false;
  metricsContent.innerHTML=`<div class="metric-grid"><div class="metric"><strong>${display(healthy)}/${display(total)}</strong>RPC responding</div><div class="metric"><strong>${display(eligible)}/${display(total)}</strong>results eligible</div><div class="metric"><strong>${display(data.verified_nodes)}</strong>verified nodes</div><div class="metric"><strong>${display(data.candidate_count)}</strong>candidates merged</div><div class="metric"><strong>${display(data.received_candidate_count??data.candidate_count)}</strong>candidates received</div><div class="metric"><strong>${display(data.elapsed_ms)} ms</strong>query time</div></div><p class="authority-version">Expected generation: <code>${display(data.expected_statistics_version)}</code></p>${data.authority_error?`<p class="diagnostic-error">${escape(data.authority_error)}</p>`:''}<div class="query-nodes">${nodes.map(renderNode).join('')}</div>${renderTrace(data)}`;
}

refreshNodes();
setInterval(refreshNodes,3000);
