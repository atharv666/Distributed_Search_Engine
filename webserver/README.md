# Web server

FastAPI served by uvicorn. It is the only component the browser talks to, and it is an outside observer of the cluster:
it has no vector clock.

```powershell
python -m webserver.server --config coordinator/config/cluster_config.json
```

| Endpoint | Purpose |
|---|---|
| `POST /api/search` | Send the query to the leader (or any live coordinator) |
| `GET /api/cluster` | Role, epoch, versions, beacon counters and vector of all six processes (polled once a second) |
| `POST /api/admin/documents` | Fetch and parse URLs (or pasted text) concurrently, then submit each to the leader |
| `POST /api/admin/processes/{id}/start\|stop` | Start or kill one coordinator or node |
| `POST /api/admin/start-all`, `stop-all`, `reset` | Cluster-wide controls; `reset` restores the original shards |
| `POST /internal/events`, `GET /api/events` | Processes push clocked events here; the admin page reads them |

Pages: `/` (search) and `/admin.html`. Open `/admin.html#add`, `#election`, `#search` or `#beacons` to jump to the latest
operation of that kind. Add `,vectors` to show full vectors on the timeline dots and `,inspect` to pre-select a message, for
example `/admin.html#add,vectors,inspect`. Logs of started processes go to `data/logs/<id>.log`.
