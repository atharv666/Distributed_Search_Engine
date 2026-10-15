# Distributed Search Engine

A distributed search engine built stage by stage. The offline pipeline prepares the corpus and the
initial statistics; the live system is three coordinators, three search nodes and a web server.

```text
ingestion_crawler -> parsing_html -> partitioning -> distributed_indexing     (offline pipeline, runs once)
                                                         |
              data/documents.jsonl, data/shards/*, data/indexes/global_statistics.json
                                                         |
Browser --HTTP--> Web server --gRPC--> C1  C2  C3 (leader)  --gRPC--> N1  N2  N3
(search + admin)  (webserver/)         (coordinator/)                 (search_node/)
```

## Run it

```powershell
python -m pip install -r requirements.txt
python -m webserver.server            # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000/admin.html> and press **Start all**. The search page is
<http://127.0.0.1:8000/>. The offline pipeline must have produced `data/` first (see the component READMEs).

Run the tests (the end-to-end one starts real processes on spare ports with a temporary copy of the data):

```powershell
python -m unittest discover -s tests -t . -v
```

## Syllabus mapping

| Topic | Where it lives |
|---|---|
| Vector clocks (Unit III) | `distributed_systems/vector_clock.py`; carried in an explicit `Stamp` field of every message (`proto/search.proto`) |
| Event ordering and causality (Unit III) | `distributed_systems/tracing.py`, timeline and event comparison on the admin page |
| Beacon / heartbeat protocol (Unit III) | `coordinator/server.py` (`_beacon_loop`, `Heartbeat`) and `search_node/server.py` |
| Election algorithm: Bully with epochs (Unit III) | `coordinator/server.py` (`start_election`, `_become_leader`, `Announce`) |
| Replication and consistency (Unit IV) | Replicated statistics deltas, version checks, epoch fencing: `distributed_systems/global_stats.py`, `ReplicateDelta`, `ApplyStatistics` |
| Distributed web-based system (Unit IV) | Browser, web server, gRPC coordinators and nodes |

## How the live system works

* **Documents.** The web server fetches and parses a URL into a document JSON. The leader assigns the document
  ID, sends the document to the least-loaded node, then computes a statistics delta (N and document frequencies),
  replicates it to the standby coordinators, and pushes it to every node. Every IDF changes when N changes, so every node
  recomputes its document norms. Each delta bumps the **statistics version**.
* **Search.** Any coordinator can serve a query. It fans out to all nodes, drops answers from nodes whose statistics
  version differs from the committed one, and merges the global top-K. Nodes score with the global IDF for every query term.
* **Beacons.** The leader sends a heartbeat to every other process every 3 s (configurable). A node or standby that hears
  nothing for 3 beats (9 s) suspects the leader.
* **Election.** A node reports the suspicion to every coordinator. A coordinator pings the leader; if it does not
  answer, it runs a Bully election (highest ID wins). The winner takes the next **epoch**, announces itself, and
  every process rejects commands from older epochs.
* **Vector clocks.** Every send, receive and local event of every coordinator and node ticks its vector clock; the
  full vector travels in `Stamp.clock`. Processes report each event to the web server, which only observes.

Settings: `coordinator/config/cluster_config.json`. See [coordinator/README.md](coordinator/README.md),
[search_node/README.md](search_node/README.md) and [webserver/README.md](webserver/README.md).

## Limits of this proof of concept

* If the leader dies after a node stored a document but before the statistics delta was replicated, that one document is
  not counted in the global statistics until it is added again.
* The web server is a single point of failure and everything runs on one machine, so there are no real network partitions.
* A search that races an in-flight add can briefly see a node on the previous statistics version and skip it.
