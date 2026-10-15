/* Inline SVG diagrams for the FA-2 slides. Each function returns an <svg> string. */
(() => {
  const C = {ink: '#15223d', blue: '#1658b6', navy: '#153e80', teal: '#07a4a1', red: '#d95d58', amber: '#efad26', green: '#2f9e44',
    light: '#e9f0ff', mint: '#e5f7f5', grey: '#8995a9', violet: '#6f42c1', lilac: '#f1ebfd', line: '#d9e2f0', pink: '#fff0ef', orange: '#ED7100'};
  const MARKERS = ['ink', 'blue', 'teal', 'red', 'grey', 'violet', 'navy', 'amber', 'green'];

  class Dg {
    constructor(id, w, h, label) { this.id = id; this.w = w; this.h = h; this.label = label; this.parts = []; }
    add(s) { this.parts.push(s); return this; }
    rect(x, y, w, h, o = {}) {
      const {fill = '#fff', stroke = C.line, rx = 12, sw = 1.5, dash, opacity} = o;
      return this.add(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ''}${opacity !== undefined ? ` opacity="${opacity}"` : ''}/>`);
    }
    text(x, y, s, o = {}) {
      const {size = 14, weight = 400, fill = C.ink, anchor = 'middle', mono, italic} = o;
      return this.add(`<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${mono ? ' font-family="ui-monospace,Consolas,monospace"' : ''}${italic ? ' font-style="italic"' : ''}>${s}</text>`);
    }
    lines(x, y, arr, o = {}, gap = 18) { arr.forEach((s, i) => this.text(x, y + i * gap, s, o)); return this; }
    line(x1, y1, x2, y2, o = {}) {
      const {color = 'ink', sw = 2, dash, arrow, both, opacity} = o;
      const hex = C[color] || color;
      const m = MARKERS.includes(color) ? color : 'ink';
      return this.add(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${hex}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ''}${opacity !== undefined ? ` opacity="${opacity}"` : ''}${arrow ? ` marker-end="url(#${this.id}-${m})"` : ''}${both ? ` marker-start="url(#${this.id}-${m})"` : ''}/>`);
    }
    path(d, o = {}) {
      const {color = 'ink', sw = 2, dash, arrow, fill = 'none'} = o;
      const hex = C[color] || color;
      const m = MARKERS.includes(color) ? color : 'ink';
      return this.add(`<path d="${d}" fill="${fill}" stroke="${hex}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ''}${arrow ? ` marker-end="url(#${this.id}-${m})"` : ''}/>`);
    }
    circle(cx, cy, r, o = {}) {
      const {fill = '#fff', stroke = C.ink, sw = 2, dash} = o;
      return this.add(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ''}/>`);
    }
    badge(cx, cy, n, fill = C.blue) { this.circle(cx, cy, 12, {fill, stroke: fill}); return this.text(cx, cy + 5, n, {size: 13, weight: 800, fill: '#fff'}); }
    pill(x, y, w, h, label, o = {}) {
      const {fill = C.light, stroke = '#c9d8f2', color = C.blue, size = 12.5, weight = 700} = o;
      this.rect(x, y, w, h, {fill, stroke, rx: h / 2, sw: 1.2});
      return this.text(x + w / 2, y + h / 2 + size * 0.35, label, {size, weight, fill: color});
    }
    svg() {
      const defs = MARKERS.map(k => `<marker id="${this.id}-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${C[k]}"/></marker>`).join('');
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${this.w} ${this.h}" role="img" aria-label="${this.label}"><defs>${defs}</defs>${this.parts.join('')}</svg>`;
    }
  }

  const D = {};

  // ---------------------------------------------------------------------------------------- FA-1 failure picture
  D.failure = () => {
    const g = new Dg('fail', 640, 372, 'The single coordinator is down and the three healthy nodes cannot be reached');
    g.rect(240, 10, 160, 46, {fill: C.light, stroke: '#b9cdf0'}).text(320, 39, 'Browser', {weight: 700});
    g.line(320, 56, 320, 112, {color: 'grey', dash: '6 5', arrow: true}).text(334, 90, 'no answer', {size: 13, fill: C.red, weight: 700, anchor: 'start'});
    g.rect(210, 112, 220, 86, {fill: C.pink, stroke: C.red, sw: 2.5, dash: '8 5'});
    g.text(320, 148, 'Coordinator', {size: 19, weight: 800}).text(320, 175, 'process stopped', {size: 14, fill: C.red, weight: 700});
    g.circle(430, 112, 17, {fill: C.red, stroke: C.red}).text(430, 118, '✖', {fill: '#fff', size: 17, weight: 800});
    [50, 250, 450].forEach((x, i) => {
      g.line(x + 70, 270, 320, 200, {color: 'grey', dash: '3 7', sw: 2});
      g.rect(x, 270, 140, 64, {fill: C.mint, stroke: C.teal, sw: 2});
      g.text(x + 70, 298, `Node ${i + 1}`, {weight: 800, size: 16}).text(x + 70, 320, 'healthy · data safe', {size: 12.5, fill: '#2b6a68'});
    });
    g.text(320, 362, 'Healthy nodes, but nobody can coordinate them', {size: 14, weight: 700, fill: C.red});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- before / after architecture
  D.before = () => {
    const g = new Dg('bef', 520, 440, 'FA-1 architecture: browser, one coordinator, three nodes');
    g.rect(170, 12, 180, 46, {fill: C.light, stroke: '#b9cdf0'}).text(260, 41, 'Browser', {weight: 700});
    g.line(260, 58, 260, 118, {color: 'blue', arrow: true}).text(248, 92, 'HTTP', {size: 12, fill: C.blue, weight: 700, anchor: 'end'});
    g.rect(98, 104, 324, 124, {fill: 'none', stroke: C.red, sw: 2, dash: '7 5'});
    g.rect(110, 118, 300, 96, {fill: C.navy, stroke: C.navy});
    g.text(260, 154, 'Coordinator', {size: 20, weight: 800, fill: '#fff'});
    g.lines(260, 178, ['web page · query merge', 'node launcher · ONE process'], {size: 12.5, fill: '#cfe0ff'}, 17);
    g.pill(268, 90, 176, 26, 'single point of failure', {fill: C.pink, stroke: '#f3b7b3', color: C.red, size: 12});
    [[30, 170], [190, 260], [350, 350]].forEach(([x, from], i) => {
      g.line(from, 228, x + 70, 316, {color: 'teal', arrow: true, both: true, sw: 1.8});
      g.rect(x, 318, 140, 74, {fill: C.mint, stroke: C.teal, sw: 1.8});
      g.text(x + 70, 348, `Node ${i + 1}`, {weight: 800, size: 16}).text(x + 70, 370, `shard ${i + 1} · local index`, {size: 12, fill: '#2b6a68'});
    });
    g.text(260, 425, 'index built once, offline, before start-up', {size: 13, fill: C.grey, italic: true});
    return g.svg();
  };

  D.after = () => {
    const g = new Dg('aft', 600, 560, 'FA-2 architecture: browser, web server, three coordinators with one leader, three nodes');
    g.rect(210, 10, 180, 44, {fill: C.light, stroke: '#b9cdf0'}).text(300, 38, 'Browser', {weight: 700});
    g.line(300, 54, 300, 90, {color: 'blue', arrow: true}).text(312, 76, 'HTTP', {size: 12, fill: C.blue, weight: 700, anchor: 'start'});
    g.rect(140, 90, 320, 68, {fill: C.lilac, stroke: '#cbb8f2', sw: 1.8});
    g.text(300, 119, 'Web server', {size: 18, weight: 800, fill: '#4b2a99'}).text(300, 141, 'FastAPI · parses URLs · finds the leader', {size: 12.5, fill: '#5b4a8a'});
    g.line(300, 158, 300, 204, {color: 'violet', arrow: true}).text(312, 186, 'gRPC', {size: 12, fill: C.violet, weight: 700, anchor: 'start'});
    g.rect(24, 204, 552, 150, {fill: '#f1f6ff', stroke: '#9db8e8', dash: '7 5', sw: 1.6});
    g.text(40, 227, 'Coordinator cluster', {size: 13.5, weight: 800, anchor: 'start', fill: C.navy});
    g.text(560, 227, 'beacons · Bully election · epochs', {size: 12, anchor: 'end', fill: C.grey});
    [['C1', 44, 'STANDBY', 'replica of the state'], ['C2', 225, 'STANDBY', 'replica of the state']].forEach(([n, x, role, sub]) => {
      g.rect(x, 242, 150, 92, {fill: '#fff', stroke: '#b9cdf0', sw: 1.6});
      g.text(x + 75, 274, n, {size: 20, weight: 800}).text(x + 75, 295, role, {size: 12, weight: 800, fill: C.grey}).text(x + 75, 316, sub, {size: 11.5, fill: C.grey});
    });
    g.rect(406, 242, 150, 92, {fill: C.navy, stroke: C.navy});
    g.text(481, 274, 'C3', {size: 20, weight: 800, fill: '#fff'}).text(481, 295, 'LEADER', {size: 12, weight: 800, fill: '#8fe9e1'}).text(481, 316, 'epoch 1 · assigns IDs', {size: 11.5, fill: '#cfe0ff'});
    g.line(194, 288, 225, 288, {color: 'blue', arrow: true, both: true}).line(375, 288, 406, 288, {color: 'blue', arrow: true, both: true});
    [44, 225, 406].forEach((x, i) => {
      g.line(481, 334, x + 75, 424, {color: 'teal', arrow: true, sw: 1.8});
      g.rect(x, 426, 150, 74, {fill: C.mint, stroke: C.teal, sw: 1.8});
      g.text(x + 75, 456, `Node ${i + 1}`, {weight: 800, size: 16}).text(x + 75, 478, `shard ${i + 1} · replica of stats`, {size: 11.5, fill: '#2b6a68'});
    });
    g.line(70, 426, 70, 336, {color: 'red', dash: '5 4', arrow: true, sw: 1.8}).text(80, 396, 'ReportSuspect', {size: 11.5, fill: C.red, anchor: 'start', weight: 700});
    g.pill(110, 523, 380, 28, 'every message carries the sender’s vector clock', {fill: C.lilac, stroke: '#cbb8f2', color: '#4b2a99'});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- Bully election in four panels
  D.bully = () => {
    const g = new Dg('bully', 1260, 372, 'Bully election in four steps with coordinators C1, C2 and C3');
    const R = 32;
    const edge = (a, b, gap = 5) => {
      const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L;
      return [a[0] + ux * (R + gap), a[1] + uy * (R + gap), b[0] - ux * (R + gap), b[1] - uy * (R + gap)];
    };
    const panels = [
      {t: '① The leader goes silent', s: 'no beacon for 9 s', states: ['alive', 'alive', 'dead'], foot: ['Nodes notice first and report;', 'C1 and C2 ping C3: no answer'], arrows: []},
      {t: '② C1 starts an election', s: 'asks only higher IDs', states: ['alive', 'alive', 'dead'], foot: ['IDs: C1 < C2 < C3', 'C3 does not answer'],
        arrows: [[0, 1, 'ELECTION', 'blue', false, 'left'], [0, 2, 'ELECTION', 'red', true, 'above']]},
      {t: '③ A higher ID takes over', s: 'C2 answers OK, then asks C3', states: ['alive', 'alive', 'dead'], foot: ['C1 stops and waits', 'for the winner'],
        arrows: [[1, 0, 'OK', 'teal', false, 'left'], [1, 2, 'ELECTION', 'red', true, 'right']]},
      {t: '④ C2 wins: epoch 2', s: 'nobody higher answered', states: ['alive', 'leader', 'dead'], foot: ['Announce (COORDINATOR) to C1 and', 'all nodes; beacons resume'],
        arrows: [[1, 0, 'Announce', 'blue', false, 'left']], nodes: true},
    ];
    panels.forEach((p, i) => {
      const px = 10 + i * 313;
      g.rect(px, 8, 296, 354, {fill: '#fff', stroke: C.line});
      g.text(px + 148, 36, p.t, {weight: 800, size: 15.5}).text(px + 148, 57, p.s, {size: 12.5, fill: C.grey});
      const pos = [[px + 66, 240], [px + 148, 132], [px + 230, 240]];
      p.arrows.forEach(([a, b, label, color, dead, side]) => {
        const [x1, y1, x2, y2] = edge(pos[a], pos[b]);
        g.line(x1, y1, x2, y2, {color, arrow: true, dash: dead ? '6 5' : undefined, sw: 2.4});
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        const place = {left: [mx - 12, my + 2, 'end'], right: [mx + 22, my + 2, 'start'], above: [mx, my - 12, 'middle']}[side];
        g.text(place[0], place[1], label, {size: 12.5, weight: 800, fill: C[color], anchor: place[2]});
        if (dead) g.text(place[0] + (side === 'above' ? 0 : 0), place[1] + (side === 'above' ? 32 : 16), '✖ no reply', {size: 12, fill: C.red, italic: true, anchor: place[2]});
      });
      if (!p.arrows.length) {          // beacons that no longer arrive
        [[2, 0], [2, 1]].forEach(([a, b]) => {
          const [x1, y1, x2, y2] = edge(pos[a], pos[b]);
          g.line(x1, y1, x2, y2, {color: 'grey', dash: '3 6', sw: 2, opacity: 0.8});
          g.text((x1 + x2) / 2, (y1 + y2) / 2 + 7, '✖', {size: 20, fill: C.red, weight: 800});
        });
      }
      ['C1', 'C2', 'C3'].forEach((name, k) => {
        const st = p.states[k], [cx, cy] = pos[k];
        const fill = st === 'dead' ? '#eceff4' : st === 'leader' ? C.navy : C.mint;
        const stroke = st === 'dead' ? C.grey : st === 'leader' ? C.navy : C.teal;
        g.circle(cx, cy, R, {fill, stroke, sw: 2.4, dash: st === 'dead' ? '5 4' : undefined});
        g.text(cx, cy + 6, name, {size: 18, weight: 800, fill: st === 'leader' ? '#fff' : st === 'dead' ? C.grey : C.ink});
        if (st === 'dead') g.text(cx, cy + 54, 'stopped', {size: 11.5, fill: C.red, weight: 700});
        if (st === 'leader') g.text(cx, cy - 42, 'LEADER', {size: 12, fill: C.navy, weight: 800});
      });
      if (p.nodes) {
        g.rect(px + 204, 112, 84, 28, {fill: C.mint, stroke: C.teal, rx: 14, sw: 1.4}).text(px + 246, 131, 'N1 · N2 · N3', {size: 12, weight: 700, fill: '#2b6a68'});
        g.line(px + 184, 126, px + 202, 126, {color: 'teal', arrow: true, sw: 2});
      }
      g.lines(px + 148, 330, p.foot, {size: 12.5, fill: '#3b4a63'}, 17);
    });
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- epochs
  D.epoch = () => {
    const g = new Dg('epoch', 1240, 392, 'Timeline of epochs: C3 leads epoch 1, C2 leads epoch 2, the stale command from C3 is rejected');
    const lane = {c3: 92, c2: 192, n: 292};
    g.text(24, lane.c3 + 5, 'C3', {size: 17, weight: 800, anchor: 'start'}).text(24, lane.c2 + 5, 'C2', {size: 17, weight: 800, anchor: 'start'}).text(24, lane.n + 5, 'N1·N2·N3', {size: 14, weight: 800, anchor: 'start'});
    [lane.c3, lane.c2, lane.n].forEach(y => g.line(90, y, 1226, y, {color: C.line, sw: 1.5}));
    // C3
    g.rect(100, lane.c3 - 26, 330, 52, {fill: C.navy, stroke: C.navy}).text(265, lane.c3 + 6, 'LEADER · epoch 1', {fill: '#fff', weight: 800, size: 15});
    g.rect(430, lane.c3 - 26, 380, 52, {fill: '#eceff4', stroke: C.grey, dash: '6 5'}).text(620, lane.c3 + 6, 'frozen or cut off from the network', {fill: C.grey, size: 14, weight: 700});
    g.circle(430, lane.c3 - 26, 13, {fill: C.red, stroke: C.red}).text(430, lane.c3 - 21, '✖', {fill: '#fff', size: 14, weight: 800});
    g.rect(810, lane.c3 - 26, 200, 52, {fill: C.pink, stroke: C.red, sw: 2}).text(910, lane.c3 - 3, 'wakes up, still believes', {size: 12.5, fill: C.red, weight: 700}).text(910, lane.c3 + 14, 'LEADER · epoch 1', {size: 13.5, fill: C.red, weight: 800});
    g.rect(1040, lane.c3 - 26, 186, 52, {fill: C.light, stroke: '#b9cdf0'}).text(1133, lane.c3 - 3, 'steps down:', {size: 12.5, weight: 700, fill: C.blue}).text(1133, lane.c3 + 14, 'STANDBY · epoch 2', {size: 13.5, weight: 800, fill: C.blue});
    // C2
    g.rect(100, lane.c2 - 26, 480, 52, {fill: '#fff', stroke: '#b9cdf0'}).text(340, lane.c2 + 6, 'STANDBY · replica of the statistics', {weight: 700, size: 14, fill: C.grey});
    g.rect(580, lane.c2 - 26, 646, 52, {fill: C.navy, stroke: C.navy}).text(740, lane.c2 + 6, 'LEADER · epoch 2', {fill: '#fff', weight: 800, size: 15});
    // nodes
    g.rect(100, lane.n - 26, 480, 52, {fill: C.mint, stroke: C.teal}).text(340, lane.n + 6, 'follow the leader of epoch 1', {weight: 700, size: 14, fill: '#2b6a68'});
    g.rect(580, lane.n - 26, 646, 52, {fill: C.mint, stroke: C.teal}).text(740, lane.n + 6, 'follow the leader of epoch 2', {weight: 700, size: 14, fill: '#2b6a68'});
    // election
    g.line(440, 156, 576, 156, {color: 'amber', sw: 2.4, arrow: true});
    g.text(508, 142, 'no beacon for 9 s → report → ping → Bully election', {size: 12.5, weight: 700, fill: '#8a5a00'});
    g.circle(580, lane.n - 26, 12, {fill: C.amber, stroke: C.amber}).text(580, lane.n - 21, '2', {size: 13, weight: 800, fill: '#fff'});
    // stale command from the old leader
    g.line(900, lane.c3 + 26, 900, lane.n - 28, {color: 'red', arrow: true, sw: 2.6});
    g.text(886, 236, 'AddDocument · ApplyStatistics', {anchor: 'end', size: 13, weight: 700, fill: C.red}).text(886, 253, 'sent with epoch 1', {anchor: 'end', size: 12.5, fill: C.red});
    g.rect(920, 330, 300, 46, {fill: C.pink, stroke: C.red, sw: 1.8}).text(1070, 350, '✖ STALE_EPOCH: rejected', {size: 14, weight: 800, fill: C.red}).text(1070, 367, 'reply carries epoch 2', {size: 12, fill: C.red});
    g.line(1150, 330, 1133, lane.c3 + 28, {color: 'blue', arrow: true, dash: '6 4', sw: 2});
    g.text(1148, 150, 'learns epoch 2', {size: 12.5, weight: 700, fill: C.blue, anchor: 'start'});
    g.pill(100, 338, 560, 30, 'Rule: reject any command whose epoch is older than the highest epoch seen', {fill: '#fff8e5', stroke: '#f1d78f', color: '#8a5a00', size: 13});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- beacon timeline
  D.beacon = () => {
    const g = new Dg('beacon', 1240, 346, 'Beacon timeline: three beacons arrive, the leader stops, nine seconds of silence trigger suspicion');
    const X = t => 120 + t * 47, lane = {l: 70, f: 160}, axis = 280;
    g.text(24, lane.l + 5, 'Leader', {size: 14, weight: 800, anchor: 'start'}).text(24, lane.f + 5, 'Others', {size: 14, weight: 800, anchor: 'start'});
    g.line(96, axis, 1226, axis, {color: 'ink', sw: 2, arrow: true});
    for (let t = 0; t <= 21; t += 3) {
      g.line(X(t), axis - 5, X(t), axis + 5, {color: 'ink', sw: 1.6}).text(X(t), axis + 24, `${t} s`, {size: 12, fill: C.grey});
    }
    g.line(96, lane.l, 1226, lane.l, {color: C.line, sw: 1.5}).line(96, lane.f, 1226, lane.f, {color: C.line, sw: 1.5});
    [0, 3, 6].forEach(t => {
      g.circle(X(t), lane.l, 9, {fill: C.green, stroke: C.green});
      g.line(X(t), lane.l + 11, X(t + 0.9), lane.f - 12, {color: 'green', arrow: true, sw: 2});
      g.circle(X(t + 1), lane.f, 9, {fill: '#fff', stroke: C.green, sw: 2.4});
      g.text(X(t), lane.l - 18, 'beacon', {size: 11.5, fill: C.green, weight: 700});
    });
    g.circle(X(7.4), lane.l, 15, {fill: C.red, stroke: C.red}).text(X(7.4), lane.l + 6, '✖', {fill: '#fff', size: 17, weight: 800});
    g.text(X(7.4), lane.l - 26, 'leader stops', {size: 12.5, fill: C.red, weight: 800});
    [9, 12, 15].forEach((t, i) => {
      g.circle(X(t), lane.l, 9, {fill: '#fff', stroke: C.red, sw: 2, dash: '3 3'});
      g.text(X(t), lane.l - 18, `missed ${i + 1}`, {size: 11.5, fill: C.red, weight: 700});
    });
    // silence counter
    g.rect(X(6), 204, X(15) - X(6), 22, {fill: '#fff4e5', stroke: '#f1d78f', rx: 6, sw: 1.4});
    [3, 6, 9].forEach(s => {
      g.line(X(6 + s), 204, X(6 + s), 226, {color: 'amber', sw: 2});
      g.text(X(6 + s), 198, `silent ${s} s`, {size: 11.5, fill: '#8a5a00', weight: 700});
    });
    g.text(X(10.5), 246, 'silence counter at every node and standby', {size: 12.5, fill: '#8a5a00', weight: 700});
    g.rect(X(15) + 54, 196, 262, 66, {fill: C.pink, stroke: C.red, sw: 1.8});
    g.text(X(15) + 185, 218, 'timeout reached (9 s)', {size: 13.5, weight: 800, fill: C.red});
    g.text(X(15) + 185, 237, 'ReportSuspect → ping → election', {size: 12.5, fill: C.red}).text(X(15) + 185, 253, 'then beacons resume', {size: 12.5, fill: C.red});
    [19, 22].forEach(t => {
      g.circle(X(t), lane.l, 9, {fill: C.navy, stroke: C.navy});
      g.line(X(t), lane.l + 11, X(t + 0.6), lane.f - 12, {color: 'navy', arrow: true, sw: 2});
    });
    g.text(X(20.5), lane.l - 26, 'new leader C2', {size: 12.5, fill: C.navy, weight: 800});
    g.text(640, 336, 'interval 3 s · 3 missed beacons → timeout 9 s', {size: 13, fill: C.grey, italic: true});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- vector clock basics
  D.vectorBasics = () => {
    const g = new Dg('vcb', 1000, 392, 'Three processes exchanging messages with vector clocks, showing before and concurrent events');
    const lane = {p1: 84, p2: 196, p3: 308};
    [['P1', lane.p1], ['P2', lane.p2], ['P3', lane.p3]].forEach(([n, y]) => {
      g.text(20, y + 6, n, {size: 19, weight: 800, anchor: 'start'}).line(66, y, 980, y, {color: C.line, sw: 1.8});
    });
    const ev = (x, y, label, vec, kind, fill = C.blue) => {
      if (kind === 'send') g.circle(x, y, 12, {fill, stroke: fill}); else if (kind === 'recv') g.circle(x, y, 12, {fill: '#fff', stroke: fill, sw: 3.2}); else g.rect(x - 10, y - 10, 20, 20, {fill, stroke: fill, rx: 3});
      g.text(x, y - 22, label, {size: 15, weight: 800, fill: C.ink}).text(x, y + 36, vec, {size: 16, mono: true, weight: 700, fill: '#344054'});
    };
    g.line(186, lane.p1 + 12, 344, lane.p2 - 13, {color: 'blue', arrow: true, sw: 2.4}).text(232, 138, 'm1', {size: 14, fill: C.blue, weight: 800});
    g.line(528, lane.p2 + 13, 684, lane.p3 - 13, {color: 'blue', arrow: true, sw: 2.4}).text(632, 254, 'm2', {size: 14, fill: C.blue, weight: 800});
    ev(170, lane.p1, 'e1', '[1,0,0]', 'send');
    ev(170, lane.p3, 'e2', '[0,0,1]', 'local', C.amber);
    ev(360, lane.p2, 'e3', '[1,1,0]', 'recv');
    ev(520, lane.p2, 'e4', '[1,2,0]', 'send');
    ev(700, lane.p3, 'e5', '[1,2,2]', 'recv');
    ev(700, lane.p1, 'e6', '[2,0,0]', 'local', C.amber);
    g.rect(760, 22, 232, 112, {fill: '#f8fbff', stroke: '#c9d8f2'});
    g.text(876, 48, 'Reading the vectors', {size: 15, weight: 800, fill: C.navy});
    g.lines(876, 74, ['e1 → e5   [1,0,0] ≤ [1,2,2]', 'e2 ∥ e1   neither ≤ the other', 'e6 ∥ e5   neither ≤ the other'], {size: 12.5, mono: true, fill: '#3b4a63'}, 24);
    g.pill(66, 354, 380, 28, '● send     ○ receive     ■ local event', {fill: '#fff', stroke: C.line, color: '#475467', weight: 600, size: 13.5});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- full architecture
  D.architecture = () => {
    const g = new Dg('arch', 1400, 840, 'Complete architecture: browser, web server, coordinator cluster, search nodes and storage');
    const layer = (y, h, label, fill, stroke) => { g.rect(110, y, 1180, h, {fill, stroke, sw: 1.6, rx: 16}); g.text(130, y + 24, label, {size: 13, weight: 800, anchor: 'start', fill: C.navy}); };
    // legend
    g.rect(14, 12, 84, 62, {fill: 'none', stroke: 'none'});
    g.line(14, 30, 54, 30, {color: 'violet', arrow: true}).text(62, 34, 'gRPC', {size: 12, anchor: 'start', fill: C.violet, weight: 700});
    g.line(14, 52, 54, 52, {color: 'red', dash: '5 4', arrow: true}).text(62, 56, 'report', {size: 12, anchor: 'start', fill: C.red, weight: 700});
    // browser
    layer(10, 74, 'BROWSER', C.light, '#b9cdf0');
    g.pill(300, 36, 380, 36, 'Search page  ·  query, ranked results, cluster badge', {fill: '#fff'});
    g.pill(700, 36, 560, 36, 'Admin console  ·  start / kill · add URL · lifecycle · vector timeline', {fill: '#fff'});
    g.line(700, 84, 700, 122, {color: 'blue', arrow: true}).text(712, 108, 'HTTP + JSON', {size: 12, weight: 700, fill: C.blue, anchor: 'start'});
    // web server
    layer(122, 176, 'WEB SERVER · FastAPI on uvicorn · outside the cluster, no vector clock', C.lilac, '#cbb8f2');
    const mod = (x, y, w, t1, t2) => { g.rect(x, y, w, 56, {fill: '#fff', stroke: '#d8c9f5', rx: 10}); g.text(x + w / 2, y + 24, t1, {size: 13.5, weight: 800, fill: '#4b2a99'}); g.text(x + w / 2, y + 43, t2, {size: 11.5, fill: '#5b4a8a'}); };
    mod(130, 158, 262, 'Search API', 'asks the leader (or any coordinator)');
    mod(407, 158, 262, 'Admin API', 'documents · processes · reset');
    mod(684, 158, 262, 'URL fetch + robots.txt', 'downloads the page');
    mod(961, 158, 306, 'HTML parser → document JSON', 'title · url · clean content');
    mod(130, 228, 340, 'Process manager', 'start / kill C1–C3 and N1–N3');
    mod(487, 228, 340, 'Cluster poller', 'GetStatus every second · finds the leader');
    mod(844, 228, 423, 'Event collector (observer)', 'receives every vector-clocked event, draws the timeline');
    g.line(700, 298, 700, 336, {color: 'violet', arrow: true}).text(712, 322, 'Search · SubmitDocument · GetStatus', {size: 12, weight: 700, fill: C.violet, anchor: 'start'});
    // coordinators
    layer(336, 212, 'COORDINATOR CLUSTER · Bully election · beacons · epochs · replicated statistics', '#eaf1fe', '#9db8e8');
    const coord = (x, name, role, lines, leader) => {
      g.rect(x, 366, 340, 142, {fill: leader ? C.navy : '#fff', stroke: leader ? C.navy : '#b9cdf0', sw: 1.8});
      g.text(x + 20, 393, `${name} · ${role}`, {size: 16, weight: 800, anchor: 'start', fill: leader ? '#fff' : C.ink});
      g.lines(x + 20, 418, lines, {size: 13, anchor: 'start', fill: leader ? '#d6e6ff' : '#3b4a63'}, 21);
    };
    coord(150, 'C1', 'STANDBY', ['• replica of N, DF and version', '• watches the beacon', '• can win an election'], false);
    coord(530, 'C2', 'STANDBY', ['• replica of N, DF and version', '• watches the beacon', '• can win an election'], false);
    coord(910, 'C3', 'LEADER · epoch 1', ['• assigns document IDs', '• picks the least-loaded node', '• computes the statistics delta', '• sends beacons every 3 s'], true);
    g.line(490, 438, 530, 438, {color: 'blue', arrow: true, both: true}).line(870, 438, 910, 438, {color: 'blue', arrow: true, both: true});
    g.text(700, 530, 'Election · Announce · Ping · ReplicateDelta · Heartbeat between coordinators', {size: 12, fill: C.navy, weight: 700});
    // coordinators -> nodes
    g.line(1080, 548, 1080, 582, {color: 'violet', sw: 2}).line(260, 582, 1080, 582, {color: 'violet', sw: 2});
    [320, 700, 1080].forEach(x => g.line(x, 582, x, 612, {color: 'violet', arrow: true, sw: 2}));
    g.text(700, 574, 'AddDocument · ApplyStatistics · Search · Heartbeat · Announce  (epoch + vector in every message)', {size: 12, weight: 700, fill: C.violet});
    // nodes
    layer(612, 156, 'SEARCH NODES · each owns one shard', '#e5f7f5', C.teal);
    const node = (x, name, shard) => {
      g.rect(x, 640, 340, 118, {fill: '#fff', stroke: '#9fd9d5', sw: 1.6});
      g.text(x + 20, 664, `${name} · ${shard}`, {size: 16, weight: 800, anchor: 'start'});
      g.lines(x + 20, 686, ['• shard file (new documents appended)', '• in-memory inverted index', '• copy of global statistics (N, DF, version)', '• delta log, replayed after a restart'], {size: 12.5, anchor: 'start', fill: '#3b4a63'}, 17);
    };
    node(150, 'N1', 'shard 1'); node(530, 'N2', 'shard 2'); node(910, 'N3', 'shard 3');
    g.path('M130,700 H66 V440 H146', {color: 'red', dash: '6 5', arrow: true, sw: 2});
    g.add('<text x="60" y="570" font-size="12" font-weight="700" fill="#d95d58" text-anchor="middle" transform="rotate(-90 60 570)">ReportSuspect (leader silent)</text>');
    // storage
    g.rect(110, 786, 1180, 44, {fill: '#fff', stroke: C.grey, dash: '6 5', rx: 10});
    g.text(700, 813, 'DISK  data/shards/*.jsonl  ·  data/state/*_deltas.jsonl  ·  global_statistics.json        →  proposed durable copy: Amazon S3', {size: 13, fill: '#475467', weight: 600});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- add-document sequence
  D.sequence = () => {
    const g = new Dg('seq', 1400, 800, 'Sequence diagram of adding one document from the admin console to a searchable state');
    const first = (window.FA2_DATA || {}).first || {doc_id: 31};
    const col = {admin: 110, web: 330, c3: 580, st: 830, n1: 1050, nn: 1262};
    const names = [['admin', 'Admin console', C.light, '#b9cdf0'], ['web', 'Web server', C.lilac, '#cbb8f2'], ['c3', 'C3 · leader', C.navy, C.navy], ['st', 'C1 · C2 standbys', '#fff', '#b9cdf0'], ['n1', 'N1 · target node', C.mint, C.teal], ['nn', 'N2 · N3', C.mint, C.teal]];
    names.forEach(([k, label, fill, stroke]) => {
      g.line(col[k], 58, col[k], 780, {color: C.line, sw: 2, dash: '5 6'});
      g.rect(col[k] - 88, 8, 176, 46, {fill, stroke, sw: 1.6}).text(col[k], 37, label, {size: 14.5, weight: 800, fill: k === 'c3' ? '#fff' : C.ink});
    });
    const msg = (n, y, a, b, label, o = {}) => {
      const color = o.color || 'violet';
      g.line(col[a], y, col[b], y, {color, arrow: true, sw: 2.4, dash: o.dash});
      g.text((col[a] + col[b]) / 2, y - 9, label, {size: 13, weight: 700, fill: C[color]});
      g.badge(col[a] + (col[b] > col[a] ? 22 : -22), y, n, C[color]);
    };
    const note = (n, y, k, w, l1, l2, o = {}) => {
      g.rect(col[k] - w / 2, y, w, l2 ? 48 : 34, {fill: o.fill || '#fffbea', stroke: o.stroke || '#f1d78f', rx: 8, sw: 1.3});
      g.badge(col[k] - w / 2 + 2, y + 2, n, o.badge || C.amber);
      g.text(col[k], y + (l2 ? 21 : 22), l1, {size: 12.5, weight: 700, fill: '#5a4300'});
      if (l2) g.text(col[k], y + 39, l2, {size: 12, fill: '#5a4300'});
    };
    msg(1, 100, 'admin', 'web', 'Add URL  (HTTP)', {color: 'grey'});
    note(2, 126, 'web', 340, 'fetch the page (robots.txt allows) · parse HTML', 'build the document JSON');
    msg(3, 214, 'web', 'c3', 'SubmitDocument(document)', {color: 'grey', dash: '7 5'});
    note(4, 242, 'c3', 330, `assign document ID ${first.doc_id}`, 'pick the least-loaded node (N1 here)');
    msg(5, 332, 'c3', 'n1', 'AddDocument(doc)  + vector');
    note(6, 350, 'n1', 210, 'index the document', 'inverted index updated');
    msg(7, 440, 'n1', 'c3', 'reply: unique terms  + vector');
    note(8, 462, 'c3', 330, 'compute the delta: N + 1, DF + 1', 'statistics version v → v + 1');
    msg(9, 546, 'c3', 'st', 'ReplicateDelta(v+1)  + vector');
    msg(10, 590, 'c3', 'n1', 'ApplyStatistics(v+1)  + vector');
    g.line(col.c3, 616, col.nn, 616, {color: 'violet', arrow: true, sw: 2.4}).text(col.nn - 4, 607, 'to N2 · N3', {size: 12.5, weight: 700, fill: C.violet, anchor: 'end'});
    note(11, 636, 'n1', 210, 'apply delta', 'recompute document norms');
    note(11, 636, 'nn', 200, 'apply delta', 'recompute norms');
    msg(12, 722, 'c3', 'web', `ok: document ${first.doc_id} → N1`, {color: 'grey', dash: '7 5'});
    msg(13, 756, 'web', 'admin', 'document is searchable', {color: 'grey'});
    g.pill(930, 90, 440, 30, 'violet arrows carry the sender’s full vector clock (Stamp)', {fill: C.lilac, stroke: '#cbb8f2', color: '#4b2a99'});
    g.pill(930, 128, 440, 30, 'grey arrows: the web server is outside the cluster', {fill: '#f4f6f9', stroke: C.line, color: '#475467'});
    return g.svg();
  };

  // ---------------------------------------------------------------------------------------- AWS deployment
  D.aws = () => {
    const g = new Dg('aws', 900, 600, 'Proposed AWS deployment: EC2 instances in three availability zones backed by an S3 bucket');
    const chip = (x, y) => { g.rect(x, y, 32, 32, {fill: C.orange, stroke: C.orange, rx: 6}); g.rect(x + 8, y + 8, 16, 16, {fill: 'none', stroke: '#fff', rx: 3, sw: 2}); };
    // users -> load balancer -> web server
    g.circle(40, 38, 11, {fill: C.light, stroke: C.blue}).path('M20,66 Q40,44 60,66', {color: 'blue', sw: 2.4, fill: C.light}).text(40, 84, 'Users', {size: 12, fill: C.grey, weight: 700});
    g.line(66, 44, 118, 44, {color: 'blue', arrow: true});
    g.rect(120, 14, 230, 62, {fill: '#fff', stroke: '#b9cdf0', sw: 1.6}).text(235, 40, 'Route 53 + load balancer', {weight: 800, size: 14}).text(235, 60, 'HTTPS entry point', {size: 12, fill: C.grey});
    g.line(350, 44, 400, 44, {color: 'blue', arrow: true});
    chip(412, 24); g.rect(404, 14, 270, 62, {fill: 'none', stroke: '#e8b98a', sw: 1.6}).text(550, 40, 'EC2 · Web server', {weight: 800, size: 14, anchor: 'middle'}).text(550, 60, 'parses URLs · finds the leader', {size: 12, fill: C.grey});
    // region
    g.rect(8, 104, 884, 400, {fill: '#fbfcfe', stroke: C.grey, dash: '8 6', rx: 16, sw: 1.6});
    g.text(24, 128, 'AWS Region', {size: 13.5, weight: 800, anchor: 'start', fill: C.navy});
    g.add('<image href="img/aws.svg" x="810" y="108" width="72" height="38" preserveAspectRatio="xMidYMid meet"/>');
    g.line(540, 76, 540, 100, {color: 'violet', sw: 2});
    // availability zones
    ['a', 'b', 'c'].forEach((z, i) => {
      const x = 24 + i * 290;
      g.rect(x, 140, 272, 222, {fill: '#fff', stroke: '#d3dcea', rx: 12, sw: 1.4});
      g.text(x + 14, 160, `Availability Zone ${z}`, {size: 12, weight: 800, anchor: 'start', fill: C.grey});
      chip(x + 14, 176); g.rect(x + 8, 170, 256, 70, {fill: 'none', stroke: '#e8b98a', rx: 10, sw: 1.4});
      g.text(x + 54, 198, `EC2 · Coordinator C${i + 1}`, {size: 14, weight: 800, anchor: 'start'}).text(x + 54, 219, i === 2 ? 'leader at start-up' : 'standby', {size: 12, fill: C.grey, anchor: 'start'});
      chip(x + 14, 262); g.rect(x + 8, 252, 256, 76, {fill: 'none', stroke: '#e8b98a', rx: 10, sw: 1.4});
      g.text(x + 54, 280, `EC2 · Search node N${i + 1}`, {size: 14, weight: 800, anchor: 'start'}).text(x + 54, 300, `shard ${i + 1} · index in memory`, {size: 12, fill: C.grey, anchor: 'start'}).text(x + 54, 316, 'statistics copy + delta log', {size: 12, fill: C.grey, anchor: 'start'});
      g.line(x + 136, 328, x + 136, 392, {color: 'green', arrow: true, both: true, dash: '5 4', sw: 2});
      g.line(540, 100, x + 136, 138, {color: 'violet', sw: 1.6, dash: '2 5'});
    });
    g.text(462, 384, 'load shard at boot · save snapshots and logs', {size: 12, weight: 700, fill: C.green, anchor: 'start'});
    // S3
    g.rect(24, 400, 852, 92, {fill: '#f2faf0', stroke: '#7aa116', sw: 2});
    g.add('<image href="img/s3.svg" x="40" y="408" width="56" height="76" preserveAspectRatio="xMidYMid meet"/>');
    g.text(116, 428, 'Amazon S3 bucket · versioning enabled', {size: 16, weight: 800, anchor: 'start', fill: '#2d5a14'});
    g.text(116, 452, 'raw/ HTML pages · documents.jsonl · shards/ · state/ (statistics snapshots + delta logs)', {size: 12.5, anchor: 'start', fill: '#3b4a63'});
    g.text(116, 474, 'Designed for 99.999999999 % (11 nines) durability · data held in ≥ 3 Availability Zones', {size: 12.5, anchor: 'start', fill: '#2d5a14', weight: 700});
    g.pill(250, 530, 400, 30, 'Proposed design: not deployed yet', {fill: C.lilac, stroke: '#cbb8f2', color: '#4b2a99'});
    return g.svg();
  };

  window.FA2_D = D;
})();
