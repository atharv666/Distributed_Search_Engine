"""Build disposable indexes and demonstrate gRPC, HTTP, clocks, and consistency.

Run from the repository root: python scripts/smoke_distributed_search.py
No crawler, external network, repository corpus, or persistent search data is used.
"""

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coordinator.engine.config import CoordinatorConfig, NodeAddress
from coordinator.engine.coordinator import SearchCoordinator
from proto import search_pb2_grpc
from tests.helpers import build_fixture, running_node, service_for


def config_for(addresses, statistics_path, timeout=0.5):
    return CoordinatorConfig(tuple(NodeAddress(f"node_{ordinal}", address)
                                   for ordinal, address in enumerate(addresses, 1)),
                             timeout, 5, 3, statistics_path)


def verify_trace(result):
    trace = result["logical_trace"]
    assert result["request_id"] and all(event["request_id"] == result["request_id"] for event in trace)
    for status in result["node_status"]:
        if status["status"] != "up":
            continue
        events = {event["event"]: event["logical_timestamp"] for event in trace
                  if event.get("node_id") == status["node_id"]}
        assert events["request_sent"] < events["request_received"] < events["response_sent"] < events["response_received"]


def summarize(label, result):
    print(f"{label}: responding={result['healthy_nodes']}/{result['total_nodes']}, "
          f"eligible={result['eligible_nodes']}, verified={result['verified_nodes']}, "
          f"results={[item['document_id'] for item in result['results']]}")
    print(f"  request_id={result['request_id']}; logical_events={len(result['logical_trace'])}; elapsed_ms={result['elapsed_ms']}")
    for status in result["node_status"]:
        print(f"  {status['node_id']}: RPC={status['status']}, "
              f"index={status['index_consistency']}, generation={status['generation_consistency']}, "
              f"accepted={status['results_accepted']}")


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def running_api(config, directory):
    """Start the project's real API entrypoint with a temporary configuration."""
    config_path = Path(directory) / "coordinator_config.json"
    config_path.write_text(json.dumps({
        "nodes": [{"node_id": node.node_id, "address": node.address} for node in config.nodes],
        "node_timeout_seconds": config.node_timeout_seconds,
        "local_top_k": config.local_top_k, "final_top_k": config.final_top_k,
        "global_statistics_file": str(config.global_statistics_file),
    }), encoding="utf-8")
    port = available_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([sys.executable, "-m", "coordinator.api_server", "--config", str(config_path),
                                "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.communicate()[0].decode("utf-8", errors="replace")
                raise RuntimeError(f"API process exited before startup:\n{output}")
            try:
                with urlopen(base_url + "/api/health", timeout=0.5) as response:
                    assert json.load(response)["status"] == "ok"
                break
            except (URLError, TimeoutError):
                time.sleep(0.05)
        else:
            raise RuntimeError("API did not become ready within 10 seconds.")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process.communicate()


def http_search(base_url):
    body = json.dumps({"query": "clock", "top_k": 3}).encode("utf-8")
    request = Request(base_url + "/api/search", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        result = json.load(response)
    with urlopen(base_url + "/", timeout=5) as response:
        assert response.status == 200 and "<html" in response.read().decode("utf-8").lower()
    with urlopen(base_url + "/app.js", timeout=5) as response:
        assert response.status == 200 and response.read()
    with urlopen(base_url + "/api/nodes", timeout=5) as response:
        assert len(json.load(response)) == 2
    invalid_body = json.dumps({"query": "clock", "top_k": 0}).encode("utf-8")
    invalid = Request(base_url + "/api/search", data=invalid_body,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        urlopen(invalid, timeout=5).close()
    except HTTPError as error:
        assert error.code == 422
        error.close()
    else:
        raise AssertionError("Invalid Top-K was not rejected by the HTTP API.")
    return result


class DelayedService(search_pb2_grpc.SearchServiceServicer):
    def __init__(self, service):
        self.service = service

    def Search(self, request, context):
        time.sleep(0.2)
        return self.service.Search(request, context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-http", action="store_true", help="Skip the local HTTP subprocess and static UI checks.")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="distributed-search-smoke-") as temporary, ExitStack() as stack:
        directory = Path(temporary)
        current = build_fixture(directory / "current")
        old = build_fixture(directory / "old", ["old clock document", "metadata old", "clock archive", "web archived"])
        first_address = stack.enter_context(running_node(service_for(current, 1)))
        second_address = stack.enter_context(running_node(service_for(current, 2)))
        config = config_for([first_address, second_address], current["statistics_path"])
        normal = SearchCoordinator(config).search("clock")
        assert (normal["healthy_nodes"], normal["eligible_nodes"], normal["verified_nodes"]) == (2, 2, 2)
        assert {item["document_id"] for item in normal["results"]} == {1, 3}
        verify_trace(normal)
        summarize("Normal gRPC search", normal)

        if not arguments.skip_http:
            with running_api(config, directory) as base_url:
                http = http_search(base_url)
                assert (http["healthy_nodes"], http["eligible_nodes"], http["verified_nodes"]) == (2, 2, 2)
                assert {item["document_id"] for item in http["results"]} == {1, 3}
                verify_trace(http)
                summarize("HTTP API and static UI", http)

        with running_node(DelayedService(service_for(current, 2))) as delayed_address:
            timeout = SearchCoordinator(config_for([first_address, delayed_address], current["statistics_path"], 0.05)).search("clock")
        assert (timeout["healthy_nodes"], timeout["eligible_nodes"]) == (1, 1)
        assert [item["document_id"] for item in timeout["results"]] == [1]
        assert any(event["event"] == "rpc_failure_observed" for event in timeout["logical_trace"])
        summarize("Node timeout with partial results", timeout)

        with running_node(service_for(old, 2)) as stale_address:
            stale = SearchCoordinator(config_for([first_address, stale_address], current["statistics_path"])).search("clock")
        assert (stale["healthy_nodes"], stale["eligible_nodes"], stale["verified_nodes"]) == (2, 1, 1)
        assert stale["node_status"][1]["index_consistency"] == "consistent"
        assert stale["node_status"][1]["generation_consistency"] == "mismatching"
        assert [item["document_id"] for item in stale["results"]] == [1]
        verify_trace(stale)
        summarize("Stale node with a matching local index/statistics pair", stale)

        index_path = current["indexes"] / "node_2_index.json"
        index_path.write_bytes(index_path.read_bytes() + b"\n")
        with running_node(service_for(current, 2)) as invalid_address:
            invalid = SearchCoordinator(config_for([first_address, invalid_address], current["statistics_path"])).search("clock")
        assert (invalid["healthy_nodes"], invalid["eligible_nodes"], invalid["verified_nodes"]) == (2, 1, 1)
        assert invalid["node_status"][1]["index_consistency"] == "inconsistent"
        assert [item["document_id"] for item in invalid["results"]] == [1]
        verify_trace(invalid)
        summarize("Changed saved index bytes", invalid)
    print("PASS: all smoke checks passed; temporary data and local services were cleaned up.")


if __name__ == "__main__":
    main()
