/* FA-2 slides (Unit 3 + Unit 4). Runs after story.js: inserts the new slides before the old conclusion and rewrites it.
   Numbers shown next to screenshots come from capture_data.js (written by scripts/capture_deck_images.py). */
(() => {
  const D = window.FA2_D;
  const deck = document.querySelector('#deck');
  const oldConclusion = slides[15];
  const PROCS = ['C1', 'C2', 'C3', 'N1', 'N2', 'N3'];
  const DATA = window.FA2_DATA || {};
  const first = DATA.first || {doc_id: 31, node: 'N1', version: 1, title: 'Event loop — Python 3.15.0 documentation', live_url: true, leader: 'C3', epoch: 1};
  const vtxt = values => `[${values.join(', ')}]`;

  const fig = (svg, cap = '', cls = '') => `<div class="figure ${cls}">${svg}${cap ? `<p class="cap">${cap}</p>` : ''}</div>`;
  const shot = (src, cap, cls = '') => `<figure class="shot ${cls}"><img src="img/${src}" alt="${cap.replace(/<[^>]*>/g, '').replace(/"/g, '&quot;')}"><figcaption>${cap}</figcaption></figure>`;
  const make = (html, cls = '') => { const s = document.createElement('section'); s.className = `slide fa-slide ${cls}`; s.innerHTML = html; return s; };

  // ---- real trace table (numbers from the captured run) --------------------------------------------------------------
  const vcell = (values, own, changed = []) => `[${values.map((v, i) => `<span class="${i === own ? 'own ' : ''}${changed.includes(i) ? 'chg' : ''}">${v}</span>`).join(', ')}]`;
  const traceTable = () => {
    const t = DATA.trace;
    if (!t) return '<div class="callout slim">Run <code>python scripts/capture_deck_images.py</code> to generate the real trace.</div>';
    const m = t.merge;
    const rows = t.rows.map(r => `<tr><td>${r.n}</td><td><b>${r.process}</b></td><td>${r.text}</td><td>${r.kind}</td><td class="v">${vcell(r.vector, r.own, r.changed)}</td></tr>${
      r.kind === 'receive' && r.process === m.process && r.n === 5 ? `<tr class="merge"><td></td><td colspan="4">local ${vtxt(m.local)} <b>max</b> message ${vtxt(m.message)} = ${vtxt(m.merged)} → <b>+1 on ${m.process}</b> → ${vtxt(m.after)}</td></tr>` : ''}`).join('');
    return `<div class="tracebox"><table class="trace"><tr><th>#</th><th>Process</th><th>Event</th><th>Kind</th><th>Vector [C1, C2, C3, N1, N2, N3]</th></tr>${rows}</table></div>`;
  };
  const ahead = (x, y) => PROCS.filter((p, i) => x[i] > y[i]);
  const concurrentCaption = () => {
    const c = DATA.concurrent;
    if (!c) return 'Inspector of the admin console: the two indexing events are concurrent.';
    return `Inspector of the admin console: ${c.a.process}’s event <code>${vtxt(c.a.vector)}</code> and ${c.b.process}’s event <code>${vtxt(c.b.vector)}</code>. ${c.a.process} is ahead in ${ahead(c.a.vector, c.b.vector).join(', ')}; ${c.b.process} is ahead in ${ahead(c.b.vector, c.a.vector).join(', ')}. Neither vector dominates, so the events are <b>concurrent</b>.`;
  };

  const slidesHtml = [];

  // 15 ── divider ------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · FA–2 · UNIT 3 + UNIT 4</p><h1>From one coordinator to a coordinated, self-healing cluster</h1>
    <p class="lead">FA–1 gave us partitioned, parallel search behind a single coordinator. FA–2 removes that single point of failure and moves the system closer to how real distributed services are run.</p>
    <div class="divider-cards">
      <article><h3>UNIT 3 · Synchronization and coordination</h3><p>Beacon (heartbeat) protocol · Bully election with epochs · vector clocks that order every message.</p></article>
      <article><h3>UNIT 4 · Real-world distributed systems</h3><p>Replicated state and consistency trade-offs · web-based architecture · proposed AWS deployment with EC2 and S3.</p></article>
      <article><h3>Live demonstration</h3><p>Kill the leader, watch the election, read the vector clocks, and add documents while the cluster heals itself.</p></article>
    </div>
    <div class="stat-band"><div><b>3</b><span>coordinators, one leader</span></div><div><b>6</b><span>processes with a vector clock</span></div><div><b>9 s</b><span>of silence before an election</span></div><div><b>21</b><span>automated tests, 11 end-to-end</span></div></div>`, 'fa-divider']);

  // 16 ── problems ---------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · FA–2 · THE PROBLEM</p><h1>Where the FA–1 architecture breaks</h1>
    <div class="fa-grid-2">
      ${fig(D.failure(), 'FA–1: one coordinator holds every connection. When it stops, three healthy nodes are cut off.', 'short')}
      <div class="problem-list">
        <div class="problem"><b>1 · Single point of failure</b><p>If the coordinator goes down there is no way to coordinate the nodes or to get data back from them. Search stops although every node is healthy.</p></div>
        <div class="problem"><b>2 · Only one coordinator</b><p>No standby, no failover target and no way to share coordination work.</p></div>
        <div class="problem"><b>3 · No way to add more coordinators</b><p>Nodes knew exactly one coordinator. With several: who is in charge, whose orders do the nodes obey, and how does a node find a replacement?</p></div>
        <div class="problem static"><b>4 · Frozen data</b><p>The indexes were built once, before start-up. New documents could not be added while the system was running.</p></div>
      </div>
    </div>
    <div class="callout"><b>What the system therefore needs</b><div class="chiprow"><span>several active coordinators</span><span>leader election</span><span>failure detection (beacons)</span><span>ordering of events (vector clocks)</span><span>replicated state</span></div></div>`]);

  // 17 ── before / after ----------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · FA–2 · ARCHITECTURE: BEFORE → AFTER</p><h1>From one coordinator to a coordinator cluster</h1>
    <div class="fa-grid-2">
      <div class="figure short"><h3>FA–1 · before</h3>${D.before()}<p class="cap">One process serves the page, merges results and launches the nodes. Lose it and everything stops.</p></div>
      <div class="figure short"><h3>FA–2 · after</h3>${D.after()}<p class="cap">The web server parses URLs, serves the pages and finds the leader. Three coordinators run a Bully election: the leader writes, the standbys replicate and can take over. Nodes follow the leader of the highest epoch.</p></div>
    </div>`]);

  // 18 ── Bully ----------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · ELECTION ALGORITHM</p><h1>The Bully algorithm: the highest live ID wins</h1>
    ${fig(D.bully(), '', 'short')}
    <div class="icards" style="margin-top:16px">
      <div class="icard accent"><h3>ELECTION</h3><p>Sent by a process that sees no leader, only to coordinators with a <b>higher</b> ID.</p></div>
      <div class="icard accent"><h3>OK</h3><p>A live, higher coordinator answers and takes over the election: it “bullies” the asker into waiting.</p></div>
      <div class="icard accent"><h3>COORDINATOR  (our <code class="k">Announce</code>)</h3><p>If nobody higher answers, the asker wins and announces itself to everyone, together with the new epoch.</p></div>
    </div>`]);

  // 19 ── election in our system ---------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · ELECTION IN OUR SYSTEM</p><h1>Who notices, who verifies, who decides</h1>
    <div class="rail c7">
      <div class="step bad"><b class="n">1</b><h3>Leader stops</h3><p>C3 is killed from the admin console (or crashes). Its beacons stop.</p></div>
      <div class="step"><b class="n">2</b><h3>Nodes notice</h3><p>After 3 missed beacons (9 s) every node suspects the leader.</p></div>
      <div class="step"><b class="n">3</b><h3>Nodes report</h3><p><code class="k">ReportSuspect</code> goes to every coordinator.</p></div>
      <div class="step"><b class="n">4</b><h3>Coordinators verify</h3><p>A coordinator <b>pings</b> the leader. An answer means a false alarm.</p></div>
      <div class="step"><b class="n">5</b><h3>Bully election</h3><p>No answer: ELECTION goes to higher IDs. The highest live ID wins.</p></div>
      <div class="step hot"><b class="n">6</b><h3>New epoch</h3><p>C2 catches up on statistics, then announces <b>epoch 2</b> to all coordinators and nodes.</p></div>
      <div class="step hot"><b class="n">7</b><h3>Service resumes</h3><p>Beacons restart and the web server finds the new leader on its next poll.</p></div>
    </div>
    <div class="icards" style="margin-top:26px">
      <div class="icard accent"><h3>Standbys watch too</h3><p>Coordinators run the same silence timer, one beat later than the nodes, so a missing report cannot stall recovery.</p></div>
      <div class="icard accent"><h3>Search keeps working</h3><p>Any live coordinator can serve queries. Only adding documents needs a leader.</p></div>
      <div class="icard accent"><h3>Revival</h3><p>A returning C3 catches up first, then bullies back with a higher epoch (epoch 3). Tested with real processes.</p></div>
    </div>`, 'roomy']);

  // 20 ── epochs -------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · EPOCHS</p><h1>Epochs: a returning old leader cannot give orders</h1>
    ${fig(D.epoch(), '', 'short')}
    <div class="icards two" style="margin-top:16px">
      <div class="icard accent"><h3>The rule</h3><p>Every command carries the sender’s <b>epoch</b> (the leader’s term number). A process remembers the highest epoch it has seen and rejects anything older with <code class="k">STALE_EPOCH</code>. The reply carries the new epoch, so the old leader steps down by itself.</p></div>
      <div class="icard warn"><h3>Why it matters</h3><p>Without epochs, a paused or cut-off leader could wake up and assign a document ID twice, or push outdated statistics. The epoch fences it off without having to kill it. Verified by a test: nodes reject epoch-1 commands once epoch 2 is announced.</p></div>
    </div>`]);

  // 21 ── beacon -----------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · BEACON (HEARTBEAT) PROTOCOL</p><h1>“I am alive” every 3 seconds</h1>
    ${fig(D.beacon(), '', 'short')}
    <div class="icards c4" style="margin-top:16px">
      <div class="icard accent"><h3>Who sends</h3><p>Only the leader: to both standby coordinators and all three nodes.</p></div>
      <div class="icard accent"><h3>What it carries</h3><p>Leader ID, epoch and the committed statistics version. The reply carries the receiver’s version, so a lagging process is caught up.</p></div>
      <div class="icard accent"><h3>Why three misses</h3><p>One lost or late beacon must not trigger an election. After 9 s of silence the ping check gives a second opinion.</p></div>
      <div class="icard accent"><h3>Visible in the UI</h3><p>Beacons sent / received counters and a countdown bar per process show the 9 s timer running.</p></div>
    </div>`]);

  // 22 ── causal ordering ------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · CAUSAL ORDERING</p><h1>Why logical time? Which event happened first?</h1>
    <div class="fa-grid-2" style="align-items:stretch">
      <div class="fa-stack">
        <p class="lead" style="font-size:1.1rem;margin:0">Coordinators and nodes are separate processes with separate clocks. Wall-clock timestamps cannot say whether the leader’s “assign ID” came before a node’s “index document”, or whether two nodes simply acted independently.</p>
        <div class="callout teal slim"><b>Lamport vs. vector:</b> one Lamport number orders causally related events but cannot tell “concurrent” from “ordered”. A vector can.</div>
      </div>
      <div class="rules"><b>Vector clock rules</b> (one counter per process)<br>① <b>local event or send</b>: own counter + 1; a send attaches the whole vector<br>② <b>receive</b>: take the element-wise <b>maximum</b> of own and received vector<br>③ then add 1 to the own counter<br><b>Compare</b>: A → B if every entry of A ≤ B (and A ≠ B). If neither vector dominates, A ∥ B: the events are <b>concurrent</b>.</div>
    </div>
    <div style="margin-top:16px">${fig(D.vectorBasics(), 'Worked example with three processes: e1 → e5 because [1,0,0] ≤ [1,2,2]; e2 ∥ e1 and e6 ∥ e5 are concurrent.', 'short')}</div>`]);

  // 23 ── vectors in our system ----------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · VECTOR CLOCKS IN OUR SYSTEM</p><h1>One vector in every message</h1>
    <div class="fa-grid-23"><div class="fa-stack">
      <p>Six processes, six counters, in the order <code class="k">[C1, C2, C3, N1, N2, N3]</code>. The web server is an outside observer and has no clock.</p>
      <pre>message Stamp {
  map&lt;string, uint64&gt; clock = 1;  // full vector
  string msg_id = 2;               // send ↔ receive
  string op     = 3;               // operation tag
  string sender = 4;
}</pre>
      <p>Every gRPC request <b>and</b> reply carries a <code class="k">Stamp</code> as an explicit field. A tracer ticks the clock on each send, receive and local event, and reports it to the admin console.</p>
      <div class="callout violet slim"><b>Also clocked:</b> beacons, elections, statistics updates and searches. The counters therefore grow over time, which is why vectors look like <code class="k">[13, 19, 59, 11, 11, 11]</code> rather than <code class="k">[0, 0, 1, 0, 0, 0]</code>.</div>
    </div>
    <div>${traceTable()}<p class="cap">${DATA.trace ? `Real trace of adding document ${DATA.trace.doc_id} (“${DATA.trace.title.replace(/</g, '&lt;')}”), captured from the running system.` : ''} Pink: entries that changed. Underlined: the process’s own counter.</p></div></div>`, 'roomy']);

  // 24 ── advantages -----------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 3 · WHY LOGICAL TIMESTAMPS?</p><h1>What vector clocks give us</h1>
    <div class="icards">
      <div class="icard accent"><h3>No synchronized clocks</h3><p>Order comes from messages, not from wall-clock time, so clock drift between machines is irrelevant.</p></div>
      <div class="icard accent"><h3>True causality</h3><p>If A happened before B then A ≤ B, and the reverse holds too: comparing two vectors tells us exactly whether they are related.</p></div>
      <div class="icard accent"><h3>Detects concurrency</h3><p>Two documents added at the same moment are shown as concurrent instead of being falsely ordered. This is the basis for spotting conflicting updates.</p></div>
      <div class="icard accent"><h3>Explains failures</h3><p>The causal trace shows what each process knew when it acted: which beacon was missed, which report started the election.</p></div>
      <div class="icard accent"><h3>Reveals stale knowledge</h3><p>A process whose vector or epoch lags is behind and must catch up before it acts.</p></div>
      <div class="icard accent"><h3>Survives restarts</h3><p>Merging by element-wise maximum rebuilds a restarted process’s knowledge from the first message it receives.</p></div>
    </div>
    <div class="callout"><b>Costs and limits:</b> the vector grows with the number of processes (6 entries here) and the counters grow with every beacon. Vector clocks order events and expose concurrency; they do not by themselves prevent deadlocks. We use them for ordering, conflict detection and diagnosis.</div>`, 'roomy']);

  // 25 ── detailed architecture -----------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ARCHITECTURE</p><h1>The complete system, top to bottom</h1>
    ${fig(D.architecture(), 'Browser → web server → coordinator cluster → search nodes. Violet arrows are gRPC messages carrying epoch and vector clock; the red dashed arrow is a node reporting a silent leader.', 'big')}`, 'compact']);

  // 26 ── add flow ----------------------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADDING A DOCUMENT</p><h1>One URL, end to end</h1>
    ${fig(D.sequence(), 'The web server does the parsing; the leader assigns the ID, chooses the node and replicates the statistics change. Two URLs submitted together run steps 5–7 in parallel on different nodes.', 'big')}`, 'compact']);

  // 27 ── replication and consistency (unit 4) --------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 4 · REPLICATION AND CONSISTENCY</p><h1>Keeping every copy of the statistics in step</h1>
    <div class="rail c5">
      <div class="step"><b class="n">1</b><h3>Compute the delta</h3><p>Leader: N + 1 and +1 document frequency for every term of the new document. Version v → v + 1.</p></div>
      <div class="step"><b class="n">2</b><h3>Replicate</h3><p>Delta goes to the standby coordinators first, so a new leader always has it.</p></div>
      <div class="step"><b class="n">3</b><h3>Push to nodes</h3><p>All nodes apply deltas strictly in order. A gap triggers a resend.</p></div>
      <div class="step"><b class="n">4</b><h3>Recompute norms</h3><p>N changed, so every IDF changed: nodes rebuild all document vector norms.</p></div>
      <div class="step hot"><b class="n">5</b><h3>Searchable</h3><p>The committed version advances; searches ignore nodes on any other version.</p></div>
    </div>
    <div class="icards two" style="margin-top:24px">
      <div class="icard accent"><h3>Replication, recovery and trade-offs</h3><ul><li>Every coordinator and node keeps the base statistics plus an ordered <b>delta log</b> on disk.</li><li>A restarted process replays its log; the leader’s next beacon reveals its version and the missing deltas are pushed.</li><li><b>Availability first:</b> reads work from any coordinator and from the live nodes; consistency is restored by catch-up and protected by version checks and epochs.</li></ul></div>
      <div class="icard warn"><h3>Honest limits</h3><ul><li>If the leader dies after a node stored a document but before the delta was replicated, that one document is not counted until it is added again.</li><li>A search racing an update can briefly skip a node that is one version behind.</li><li>Same idea as version stamps in GFS and HDFS: a replica with an old version is not trusted.</li></ul></div>
    </div>`, 'roomy']);

  // 28 ── AWS -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · UNIT 4 · REAL-WORLD DEPLOYMENT (PROPOSED)</p><h1>Running it on AWS: EC2 plus S3</h1>
    <div class="fa-grid-32" style="grid-template-columns:1.6fr 1fr">
      ${fig(D.aws(), 'Coordinators and nodes are spread over three Availability Zones. S3 holds the data that must survive any single machine.', 'big')}
      <div class="fa-stack">
        <div class="rail c3" style="grid-template-columns:1fr">
          <div class="step bad"><b class="n">1</b><h3>An EC2 instance fails</h3><p>Beacons stop; the cluster elects a new leader if it was a coordinator, and search continues on the healthy nodes.</p></div>
          <div class="step"><b class="n">2</b><h3>A replacement is launched</h3><p>A launch template starts a fresh EC2 instance; its start-up script copies the shard and the latest snapshot from S3.</p></div>
          <div class="step hot"><b class="n">3</b><h3>It catches up and rejoins</h3><p>The process replays its delta log, the leader’s beacon shows its version, and the missing deltas are pushed.</p></div>
        </div>
        <div class="callout teal slim"><b>Why S3:</b> S3 Standard is designed for 99.999999999 % (11 nines) durability and stores objects across at least three Availability Zones, with 99.99 % designed availability. It is the safe copy; EC2 disks are disposable.</div>
      </div>
    </div>`]);

  // 29 ── unit 3 mapping --------------------------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · FA–2 · UNIT 3</p><h1>Applying Unit 3: synchronization and coordination</h1>
    <table class="mapping"><tr><th>Unit 3 topic</th><th>Evidence in our project</th><th>Status</th></tr>
      <tr><td>Logical clocks, vector algorithm</td><td>A <code>Stamp</code> with the full vector in every gRPC message; live causal timeline, event comparison (before / after / concurrent).</td><td><span class="tag done">IMPLEMENTED</span></td></tr>
      <tr><td>Election algorithms</td><td>Bully election among C1–C3, extended with epochs to fence off stale leaders.</td><td><span class="tag done">IMPLEMENTED</span></td></tr>
      <tr><td>Beacon protocol</td><td>Leader beacon every 3 s, suspicion after 9 s of silence, counters and countdown bars in the admin console.</td><td><span class="tag done">IMPLEMENTED</span></td></tr>
      <tr><td>Mutual exclusion</td><td>Only the elected leader accepts writes (single writer). A classic algorithm such as Ricart–Agrawala is not used.</td><td><span class="tag part">LEADER-BASED</span></td></tr>
      <tr><td>Global state</td><td>Per-process status and a causal trace of events. We do not take Chandy–Lamport snapshots.</td><td><span class="tag no">NOT DONE</span></td></tr>
    </table>`, 'roomy']);

  // 30 ── unit 4 mapping ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · FA–2 · UNIT 4</p><h1>Applying Unit 4: real-world distributed systems</h1>
    <table class="mapping"><tr><th>Unit 4 topic</th><th>Evidence in our project</th><th>Status</th></tr>
      <tr><td>Distributed web-based systems</td><td>Browser → stateless web server → gRPC coordinators → nodes. The HTTP front end is separate from the coordination logic.</td><td><span class="tag done">IMPLEMENTED</span></td></tr>
      <tr><td>Replication and consistency trade-offs</td><td>Statistics deltas replicated to standbys and nodes, version checks on every search, epoch fencing; availability favoured over strict consistency.</td><td><span class="tag done">IMPLEMENTED</span></td></tr>
      <tr><td>Cloud case study: AWS</td><td>EC2 instances across three Availability Zones with S3 as durable store; failure recovery through replacement instances.</td><td><span class="tag plan">DESIGNED</span></td></tr>
      <tr><td>Distributed storage ideas (GFS, HDFS)</td><td>S3 plays the durable-storage role; version numbers identify stale replicas, as chunk versions do in GFS and generation stamps in HDFS.</td><td><span class="tag part">CONCEPT</span></td></tr>
      <tr><td>Kubernetes</td><td>Containerising coordinators and nodes (a StatefulSet for nodes) is the natural next deployment step.</td><td><span class="tag plan">FUTURE WORK</span></td></tr>
    </table>`, 'roomy']);

  // 31 ── two pages ------------------------------------------------------------------------------------------------------------------
  const searchCaption = `<b>Search page</b> (<code>/</code>): served by ${first.leader}, leader of epoch ${first.epoch}, statistics v${first.version}, 3/3 nodes answered. The ${first.live_url ? 'page added from a live URL' : 'document added a moment earlier'} (document ${first.doc_id}, node ${first.node}) ranks first.`;
  slidesHtml.push([`<p class="kicker">{{n}} · THE RUNNING SYSTEM</p><h1>Two pages: search for users, admin for operators</h1>
    <div class="fa-grid-2">
      <div>${shot('search.png', searchCaption)}</div>
      <div class="fa-stack">${shot('admin_overview.png', '<b>Admin console</b> (<code>/admin.html</code>): one card per process, with live role, epoch, beacon counters and vector clock; Start / Kill for every coordinator and node.')}
        <div class="callout slim blue"><b>Node controls moved here.</b> The search page no longer starts or stops nodes; operators do that from the admin console.</div></div>
    </div>`]);

  // 32 ── admin: processes ---------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · PROCESSES</p><h1>Control and observe every process</h1>
    ${shot('admin_overview.png', '')}
    <div class="icards c4" style="margin-top:14px">
      <div class="icard accent"><h3>Leader and epoch</h3><p>The leader’s card is highlighted; the summary shows leader, epoch, statistics version and processes up.</p></div>
      <div class="icard accent"><h3>Beacon counters</h3><p>The leader shows beacons sent and which nodes replied; everyone else shows beacons received and a bar counting down to the 9 s timeout.</p></div>
      <div class="icard accent"><h3>Live vector clock</h3><p>Every card shows that process’s current vector, in the order C1 … N3, with its own entry underlined.</p></div>
      <div class="icard accent"><h3>Start / Kill</h3><p>Any coordinator or node can be killed and restarted to demonstrate failure handling.</p></div>
    </div>`, 'compact']);

  // 33 ── add lifecycle ---------------------------------------------------------------------------------------------------------------------
  const titleEsc = first.title.replace(/</g, '&lt;');
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · ADDING A DOCUMENT</p><h1>Watching a URL become a searchable document</h1>
    <div class="fa-grid-2">
      <div>${shot('admin_lifecycle.png', 'Lifecycle panel: the web server’s steps (no vector clock) come first, then the leader’s steps with the vector clock on every line.')}</div>
      <div class="fa-stack">
        <div class="rules"><b>Document JSON built by the web server</b>
<pre style="background:transparent;padding:6px 0 0;margin:0;color:#d9ecff">{
  "title": "${titleEsc}",
  "url": "${first.live_url ? 'https://docs.python.org/3/library/asyncio-eventloop.html' : 'text://admin'}",
  "source": "admin",
  "content": "…clean visible text…",
  "content_length": …
}
<b>document_id</b> is added by the leader: ${first.doc_id}</pre></div>
        <div class="callout teal slim"><b>Then:</b> the leader routes it to the least-loaded node (${first.node}), computes the statistics delta, replicates it to C1 and C2, and pushes it to N1–N3. Search finds it immediately.</div>
      </div>
    </div>`]);

  // 34 ── concurrency ---------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · CONCURRENT EVENTS</p><h1>Two documents at once: concurrent, not ordered</h1>
    <div class="fa-stack">
      <p class="lead" style="font-size:1.12rem">“Add 2 sample texts at once” sends both documents to different nodes in parallel. Neither indexing event caused the other, and the vector clocks prove it.</p>
      ${shot('admin_concurrent.png', concurrentCaption())}
      <div class="callout violet slim"><b>Why a single Lamport number is not enough:</b> sorting by it (with a tie-break) always produces an order, even between events that were independent. Vectors do not pretend.</div>
    </div>`]);

  // 35 ── timeline of an add -----------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · VECTOR TIMELINE</p><h1>The whole add as a causal diagram</h1>
    ${shot('admin_add_timeline.png', '')}
    <div class="icards" style="margin-top:14px">
      <div class="icard accent"><h3>How to read it</h3><p>One lane per process, one dot per event: ● send, ○ receive, ◆ local. Arrows are messages; the number under a dot is that process’s own counter.</p></div>
      <div class="icard accent"><h3>What you see</h3><p>C3 sends the document to ${first.node}, hears back, then replicates to C1 and C2 and pushes the new statistics to all three nodes.</p></div>
      <div class="icard accent"><h3>Replay</h3><p>The console can animate the diagram step by step, which is useful on stage.</p></div>
    </div>`, 'compact']);

  // 36 ── vectors on the dots ----------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · FULL VECTORS</p><h1>Zoom in: the whole vector on every event</h1>
    ${shot('admin_vectors.png', 'One search (C3 → N1, N2, N3 and back). Only the processes that took part get a lane. Pink entries changed at that event; the underlined entry is the process’s own counter.')}
    <div class="callout violet slim"><b>Reading one arrow:</b> when a node receives the query it takes the entry-wise maximum of its own vector and the leader’s, then adds one to its own entry. That is why its vector suddenly “learns” the leader’s counter.</div>`, 'compact']);

  // 37 ── trace table -------------------------------------------------------------------------------------------------------------------------------------------
  const merge = (DATA.trace || {}).merge;
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · VECTOR TRACE</p><h1>Every event, its rule and its vector</h1>
    ${shot('admin_trace.png', '')}
    <div class="callout violet slim"><b>Check it by hand:</b> local ${merge ? `<code class="k">${vtxt(merge.local)}</code>` : ''} <b>max</b> message ${merge ? `<code class="k">${vtxt(merge.message)}</code>` : ''} = ${merge ? `<code class="k">${vtxt(merge.merged)}</code>` : ''}, then +1 on ${merge ? merge.process : 'the receiver'} gives ${merge ? `<code class="k">${vtxt(merge.after)}</code>` : ''}. Rules: <b>local</b> own +1 · <b>send</b> own +1 and attach the vector · <b>receive</b> max, then own +1.</div>`, 'compact']);

  // 38 ── failover overview ---------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · FAILOVER DEMO</p><h1>Kill the leader, watch the election</h1>
    ${shot('failover_overview.png', '<b>After killing C3:</b> C3 is stopped, C2 is LEADER at epoch 2, and C1, N1, N2, N3 follow C2. Statistics version and document counts are unchanged.')}
    <div class="icards" style="margin-top:12px">
      <div class="icard bad"><h3>Before</h3><p>C3 leader · epoch 1 · 6 / 6 processes up</p></div>
      <div class="icard warn"><h3>≈ 9 s of silence</h3><p>Nodes suspect, coordinators ping, Bully election runs</p></div>
      <div class="icard accent"><h3>After</h3><p>C2 leader · epoch 2 · 5 / 6 up · search and adds keep working</p></div>
    </div>`, 'compact']);

  // 39 ── failover lifecycle --------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · FAILOVER STEPS</p><h1>What the nodes noticed first</h1>
    <div class="fa-grid-2">
      <div>${shot('failover_steps.png', 'Lifecycle of the failover in the admin console: nodes N1, N2 and N3 each suspect the silent leader after 9 s and report it to the coordinators.')}</div>
      <div class="fa-stack">
        <div class="icard accent"><h3>Detection</h3><p>Every node has its own silence timer. The first to expire sends <code class="k">ReportSuspect</code> to all coordinators.</p></div>
        <div class="icard accent"><h3>Verification</h3><p>A coordinator pings C3. When the ping fails it starts the Bully election; other reports arrive while it is busy and are ignored as “already handling”.</p></div>
        <div class="icard accent"><h3>Decision</h3><p>C2 wins, announces epoch 2 and the beacons resume. Each step is an event with a vector clock, so the order is provable.</p></div>
      </div>
    </div>`]);

  // 40 ── election timeline ---------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · ADMIN CONSOLE · ELECTION TIMELINE</p><h1>The election as a causal diagram</h1>
    ${shot('failover_timeline.png', 'Vector-clock timeline of the failover. C3 has no lane because a dead process produces no events. Left: nodes report, coordinators ping and send ELECTION. Right: C2 announces epoch 2 and every process acknowledges.')}
    <div class="icards" style="margin-top:12px">
      <div class="icard accent"><h3>Left cluster of arrows</h3><p>N1–N3 → C1, C2 (<code class="k">ReportSuspect</code>), then pings and ELECTION messages between coordinators.</p></div>
      <div class="icard accent"><h3>Missing lane</h3><p>C3 does not appear at all: no events, no vector entries beyond what it sent before it died.</p></div>
      <div class="icard accent"><h3>Right cluster</h3><p>C2 → C1, N1, N2, N3: the <code class="k">Announce</code> of epoch 2 and the acknowledgements.</p></div>
    </div>`, 'compact']);

  // 41 ── demo script -----------------------------------------------------------------------------------------------------------------------------------------------------------
  slidesHtml.push([`<p class="kicker">{{n}} · LIVE DEMO SCRIPT</p><h1>What we will show, in order</h1>
    <div class="demo-list">
      <div><div><b>Start all</b><p>Admin console → “Start all”.</p></div><p class="say">Six processes come up, C3 is elected leader (epoch 1) and the beacon counters start rising.</p></div>
      <div><div><b>Search</b><p>Search page: “asyncio event loop”.</p></div><p class="say">Served by the leader; the node table shows all three shards answering with the same statistics version.</p></div>
      <div><div><b>Add a URL</b><p>Admin → paste a docs.python.org URL → Add.</p></div><p class="say">Lifecycle: fetch → JSON → ID → least-loaded node → statistics version +1. Search finds it at once.</p></div>
      <div><div><b>Two adds at once</b><p>“Add 2 sample texts at once”, then “Compare last two adds”.</p></div><p class="say">The two indexing events are concurrent: neither vector dominates.</p></div>
      <div><div><b>Kill the leader</b><p>Kill C3, watch the countdown bars.</p></div><p class="say">After 9 s nodes report, coordinators ping and elect C2 at epoch 2. Search still works throughout.</p></div>
      <div><div><b>Revive C3</b><p>Start C3.</p></div><p class="say">It catches up on missed statistics, then bullies back with epoch 3.</p></div>
      <div><div><b>Kill a node</b><p>Kill N3, add a document, restart N3.</p></div><p class="say">The leader marks N3 down and routes elsewhere; on restart a beacon shows N3 is behind and pushes the missing deltas.</p></div>
    </div>`, 'compact']);

  // build and insert ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  const nodes = slidesHtml.map(([html, cls], i) => make(html.replace('{{n}}', String(15 + i)), cls || ''));
  nodes.forEach(node => deck.insertBefore(node, oldConclusion));
  slides.splice(15, 0, ...nodes);

  // rewritten conclusion (the old FA-2 "roadmap" has now been delivered)
  oldConclusion.className = 'slide fa-slide roomy';
  oldConclusion.innerHTML = `<p class="kicker">${15 + slidesHtml.length} · CONCLUSION</p><h1>A search engine that now coordinates itself</h1>
    <div class="icards">
      <div class="icard accent"><h3>FA–1 · delivered</h3><ul><li>Controlled crawl and logical documents</li><li>Shard-local inverted indexes</li><li>Global TF-IDF and cosine ranking</li><li>Independent gRPC nodes, parallel query fan-out</li></ul></div>
      <div class="icard accent"><h3>FA–2 · delivered</h3><ul><li>Three coordinators, Bully election with epochs</li><li>Beacon protocol: 3 s interval, 9 s timeout</li><li>Vector clocks on every message, live causal timeline</li><li>Replicated statistics with versions and catch-up</li><li>Live document ingestion and an admin console</li><li>21 automated tests, 11 of them end-to-end with real failures</li></ul></div>
      <div class="icard warn"><h3>Next steps</h3><ul><li>Deploy on AWS: EC2 + S3 (designed, not yet built)</li><li>Containers and Kubernetes for nodes and coordinators</li><li>Consensus (for example Raft) for coordinator state</li><li>Replicate shards across nodes</li></ul></div>
    </div>
    <p class="closing">The system is distributed because independent processes own partitions, communicate through RPC, agree on one leader despite failures, and can reason about the order of what happened, while staying useful during partial failure.</p>
    <h2 class="thanks">Thank you · Questions?</h2>
    <p class="credits">Cloud logos: Wikimedia Commons (see img/CREDITS.txt). All screenshots are of this project’s own interface.</p>`;

  // cover: now covers both assessments
  const cover = slides[0];
  cover.querySelector('.kicker').textContent = 'DISTRIBUTED SYSTEMS · FA–1 + FA–2 MINI PROJECT';
  cover.querySelector('h2').textContent = 'Partitioned indexing · coordinator election · vector-clock ordering';

  // FA-1 demo slide: replace the screenshot placeholder with the real admin console
  const placeholder = slides[14].querySelector('.placeholder');
  if (placeholder) {
    placeholder.outerHTML = `<div style="margin-top:22px">${shot('admin_overview.png', 'Node controls now live in the admin console: Start / Kill for every process, with live role, epoch and beacon status.', 'crop')}</div>`;
  }

  // index.html?pdf hides the navigation chrome (used by scripts/export_deck_pdf.py)
  if (location.search.includes('pdf')) document.body.classList.add('pdf');

  // slide count changed: refresh the counter and honour a deep link such as #25
  show(Math.min(Math.max(0, initialSlide - 1), slides.length - 1));
})();
