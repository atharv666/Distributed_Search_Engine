# Coordinator

Three coordinator processes run (`C1`, `C2`, `C3`). The highest live ID is the leader; the others are standbys that hold a
replica of the global statistics so any of them can take over.

```powershell
python -m coordinator.server --id C3 --config coordinator/config/cluster_config.json
```

Normally you start them from the admin page instead.

## Roles

| Role | Does |
|---|---|
| LEADER | Accepts documents (`SubmitDocument`), assigns IDs, picks the node, computes and replicates statistics deltas, sends beacons |
| STANDBY | Applies replicated deltas, watches the beacon, answers searches, takes part in elections |
| CANDIDATE | A standby that is running an election |

## Messages (`proto/search.proto`, `CoordinatorService`)

`Heartbeat`, `Election`, `Announce`, `Ping`, `ReportSuspect`, `ReplicateDelta`, `GetDeltasSince`, `SubmitDocument`,
`Search`, `GetStatus`. Every message between cluster members carries a `Stamp` holding the sender's vector clock.
`SubmitDocument`, `Search` (from the web server) and `GetStatus` come from outside the cluster and are not clocked.

## Election

1. A node misses 3 beacons and sends `ReportSuspect` to every coordinator (standbys also notice, one beat later).
2. A coordinator `Ping`s the leader. If it answers as leader, nothing happens.
3. Otherwise the coordinator sends `Election` to every higher ID. Any that answers OK takes over the election.
4. If nobody higher answers, it wins: it first catches up on missed statistics deltas, then `Announce`s a new epoch
   (`highest epoch + 1`) to every coordinator and node, and starts its beacon.
5. A revived higher-ID coordinator repeats this and takes leadership back with a higher epoch.

## Settings

`cluster_config.json`: process addresses, `heartbeat_interval_seconds` (3), `missed_beats_before_suspect` (3, so a 9 s
timeout), RPC timeout, election wait, top-K. Relative paths resolve from the folder containing the file.
