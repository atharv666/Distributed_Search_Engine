"""Capture the real UI screenshots (and the numbers shown in them) used by the presentation.

It starts a disposable cluster (own ports, temporary copy of the data, 3 s beacons like the real
configuration), adds a live web page and two documents at once, kills the leader, and photographs
the pages with headless Edge into ppt/img/. It also writes ppt/capture_data.js with the exact
vectors and IDs that appear in those screenshots, so the slide text always matches the pictures.
Nothing in the real data/ folder is changed.

Usage:  python scripts/capture_deck_images.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.helpers import WEB_PORT, WebServer, make_workspace, wait_for  # noqa: E402

OUT = ROOT / "ppt" / "img"
DATA_JS = ROOT / "ppt" / "capture_data.js"
EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)
SCALE = 1.6
BACKGROUND = (244, 247, 251)
PROCS = ["C1", "C2", "C3", "N1", "N2", "N3"]


def photograph(name: str, path: str, width: int, height: int, crop: bool = True, wait_ms: int = 9000, top_css_px: int = 0) -> None:
    raw = OUT / f"_{name}.png"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={SCALE}",
                    f"--window-size={width},{height}", f"--virtual-time-budget={wait_ms}", f"--screenshot={raw}",
                    f"http://127.0.0.1:{WEB_PORT}{path}"], capture_output=True, timeout=120)
    image = Image.open(raw).convert("RGB")
    if crop:           # trim the empty page background around the focused panel
        difference = ImageChops.difference(image, Image.new("RGB", image.size, BACKGROUND)).convert("L")
        box = difference.point(lambda value: 255 if value > 10 else 0).getbbox()
        if box:
            pad = int(10 * SCALE)
            image = image.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(image.width, box[2] + pad), min(image.height, box[3] + pad)))
    if top_css_px and image.height > top_css_px * SCALE:      # keep only the first rows of a long list
        image = image.crop((0, 0, image.width, int(top_css_px * SCALE)))
    if image.width > 2000:
        image = image.resize((2000, round(image.height * 2000 / image.width)), Image.LANCZOS)
    image.save(OUT / f"{name}.png", optimize=True)
    raw.unlink()
    print(f"{name}.png  {image.width}x{image.height}")


def vector(event: dict) -> list[int]:
    return [event["vector"].get(p, 0) for p in PROCS]


def latest_add_trace(events: list[dict], leader: str) -> dict:
    """The rows and the merge arithmetic of the most recent add, exactly as the admin console shows them."""
    ops: dict[str, list[dict]] = {}
    for event in events:
        if event["op"].startswith("doc-"):
            ops.setdefault(event["op"], []).append(event)
    op = max(ops, key=lambda key: max(e["time"] for e in ops[key]))
    mine = [e for e in ops[op] if e["vector"]]
    by_process: dict[str, list[dict]] = {}
    for event in events:
        if event["vector"]:
            by_process.setdefault(event["process"], []).append(event)
    for items in by_process.values():
        items.sort(key=lambda e: e["seq"])

    def previous(event):
        items = by_process[event["process"]]
        index = items.index(event)
        return items[index - 1] if index else None

    def pick(name, process=None):
        return next(e for e in mine if e["name"] == name and (process is None or e["process"] == process))

    received = pick("document_received")
    assigned = pick("doc_id_assigned")
    selected = pick("node_selected")
    node = selected["details"]["node"]
    sent = pick("add_document_sent")
    node_received = pick("add_document_received", node)
    indexed = pick("document_indexed", node)
    reply_sent = pick("add_document_reply_sent", node)
    reply_received = pick("add_document_reply_received", leader)
    doc_id = assigned["details"]["doc_id"]
    steps = [
        (received, "receives the document", "local"), (assigned, f"assigns document ID {doc_id}", "local"),
        (selected, f"picks the least-loaded node ({node})", "local"), (sent, f"sends the document → {node}", "send"),
        (node_received, f"receives the document ← {leader}", "receive"), (indexed, "indexes it", "local"),
        (reply_sent, f"confirms indexing → {leader}", "send"), (reply_received, f"receives the confirmation ← {node}", "receive"),
    ]
    rows = []
    for number, (event, text, kind) in enumerate(steps, start=1):
        before = previous(event)
        before_vector = vector(before) if before else [0] * 6
        after = vector(event)
        rows.append({"n": number, "process": event["process"], "text": text, "kind": kind, "vector": after,
                     "own": PROCS.index(event["process"]), "changed": [i for i in range(6) if after[i] != before_vector[i]]})
    before_receive = previous(node_received)
    local = vector(before_receive) if before_receive else [0] * 6
    message = vector(sent)
    return {"op": op, "doc_id": doc_id, "node": node, "title": received["details"].get("title", ""), "rows": rows,
            "merge": {"process": node, "local": local, "message": message,
                      "merged": [max(a, b) for a, b in zip(local, message)], "after": vector(node_received)}}


def concurrent_pair(events: list[dict]) -> dict:
    indexed = [e for e in events if e["name"] == "document_indexed"]
    ops = list(dict.fromkeys(e["op"] for e in reversed(indexed)))[:2]
    picks = [next(e for e in reversed(indexed) if e["op"] == op) for op in ops]
    return {"a": {"process": picks[0]["process"], "vector": vector(picks[0]), "doc_id": picks[0]["details"]["doc_id"]},
            "b": {"process": picks[1]["process"], "vector": vector(picks[1]), "doc_id": picks[1]["details"]["doc_id"]}}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="ds_deck_"))
    web = WebServer(make_workspace(workspace, heartbeat_seconds=3.0))
    web.start()
    data: dict = {}
    try:
        web.post("/api/admin/start-all")
        wait_for(lambda: web.cluster()["leader"] and sum(p["state"] == "running" for p in web.cluster()["processes"]) == 6,
                 60, "cluster did not come up")
        time.sleep(8)

        # 1. one real web page (exercises fetch + parse); it must rank first for the demo query, else fall back to text
        real = web.post("/api/admin/documents", {"urls": ["https://docs.python.org/3/library/asyncio-eventloop.html"]})
        outcome = real["results"][0]
        print("real url:", outcome["ok"], outcome.get("error"), outcome.get("doc_id"), outcome.get("node_id"), outcome.get("content_length"))
        ranked = web.post("/api/search", {"query": "asyncio event loop"})["results"] if outcome["ok"] else []
        if not ranked or ranked[0]["document_id"] != outcome.get("doc_id"):
            print("live page did not rank first; adding a text document instead")
            outcome = web.post("/api/admin/documents", {"texts": [{"title": "Event loop - Python asyncio", "content": "The asyncio event loop runs asynchronous tasks and callbacks, performs network IO and runs subprocesses. Coroutines are scheduled on the event loop and the loop is the core of every asyncio application."}]})["results"][0]
        web.post("/api/search", {"query": "asyncio event loop"})
        time.sleep(5)
        events = web.all_events()
        leader = web.cluster()["leader"]
        data["first"] = {"doc_id": outcome["doc_id"], "node": outcome["node_id"], "version": outcome["version"], "title": outcome.get("title", ""),
                         "live_url": bool(real["results"][0]["ok"] and outcome is real["results"][0]), "leader": leader,
                         "epoch": web.cluster()["epoch"]}
        data["trace"] = latest_add_trace(events, leader)

        photograph("search", "/index.html?q=asyncio+event+loop", 1300, 900, crop=False, wait_ms=6000)
        photograph("admin_overview", "/admin.html#add,focus=summary+processes-panel", 1500, 1700)
        photograph("admin_lifecycle", "/admin.html#add,full,focus=lifecycle-panel", 900, 3200, top_css_px=700)
        photograph("admin_add_timeline", "/admin.html#add,focus=timeline-panel", 1500, 1700)
        photograph("admin_vectors", "/admin.html#search,vectors,focus=timeline-panel", 1400, 1700)
        photograph("admin_trace", "/admin.html#add,focus=trace-panel", 1500, 1700)

        # 2. two documents added at the same moment
        pair = web.post("/api/admin/documents", {"texts": [
            {"title": "Raft consensus primer", "content": "Raft elects a leader with randomized timeouts and replicates a log to followers, so a majority quorum can always agree on the same committed entries."},
            {"title": "Gossip protocols overview", "content": "Gossip protocols spread membership and failure information epidemically, with every peer repeatedly sharing state with a few random neighbours until the whole cluster converges."}]})
        print("pair:", [(r["ok"], r.get("doc_id"), r.get("node_id"), r.get("version")) for r in pair["results"]])
        time.sleep(5)
        data["concurrent"] = concurrent_pair(web.all_events())
        data["versionAfterPair"] = web.cluster()["stats_version"]
        photograph("admin_concurrent", "/admin.html#concurrent,focus=compare", 1500, 1500)

        # 3. kill the leader and photograph the failover
        web.post("/api/admin/processes/C3/stop")
        wait_for(lambda: web.cluster()["leader"] == "C2", 90, "C2 should take over")
        time.sleep(5)
        photograph("failover_overview", "/admin.html#election,focus=summary+processes-panel", 1500, 1700)
        photograph("failover_timeline", "/admin.html#election,focus=timeline-panel", 1500, 1700)
        photograph("failover_steps", "/admin.html#election,focus=lifecycle-panel", 900, 1500)
    finally:
        web.stop()
    DATA_JS.write_text("/* generated by scripts/capture_deck_images.py: the numbers shown in ppt/img/*.png */\nwindow.FA2_DATA = "
                       + json.dumps(data, indent=1) + ";\n", encoding="utf-8")
    print("wrote", DATA_JS.name)


if __name__ == "__main__":
    main()
