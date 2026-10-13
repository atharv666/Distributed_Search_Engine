"""Route-level API checks without introducing an HTTP client dependency."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from coordinator import api_server
from coordinator.engine.config import CoordinatorConfig, NodeAddress


class ApiTests(unittest.TestCase):
    def test_windows_node_stop_terminates_tracked_process_tree(self):
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch.object(api_server, "node_processes", {"node_1": process}), \
                patch.object(api_server.sys, "platform", "win32"), \
                patch.object(api_server.subprocess, "run", return_value=Mock(returncode=0)) as terminate_tree:
            result = api_server.stop_node("node_1")
            self.assertNotIn("node_1", api_server.node_processes)
        self.assertEqual(result["state"], "stopped")
        terminate_tree.assert_called_once_with(
            ["taskkill", "/PID", "12345", "/T", "/F"], capture_output=True, text=True,
        )
        process.wait.assert_called_once_with(timeout=3)
        process.terminate.assert_not_called()

    def test_windows_node_stop_failure_is_reported(self):
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch.object(api_server, "node_processes", {"node_1": process}), \
                patch.object(api_server.sys, "platform", "win32"), \
                patch.object(api_server.subprocess, "run", return_value=Mock(returncode=1, stderr="Access denied")), \
                self.assertRaisesRegex(RuntimeError, "Access denied"):
            api_server.stop_node("node_1")

    def test_node_launch_uses_selected_data_directory(self):
        directory = Path("runtime") / "data"
        with patch.object(api_server, "DATA_DIRECTORY", directory):
            arguments = api_server.node_launch_arguments("node_2")
        self.assertEqual(arguments[arguments.index("--port") + 1], "50052")
        self.assertEqual(arguments[arguments.index("--index") + 1], str(directory / "indexes/nodes/node_2_index.json"))
        self.assertEqual(arguments[arguments.index("--shard") + 1], str(directory / "shards/shard_2.jsonl"))
        self.assertEqual(arguments[arguments.index("--statistics") + 1], str(directory / "indexes/global_statistics.json"))

    def test_unconfigured_search_returns_service_unavailable(self):
        with patch.object(api_server, "coordinator", None), self.assertRaises(HTTPException) as caught:
            api_server.search(api_server.SearchBody(query="clock"))
        self.assertEqual(caught.exception.status_code, 503)

    def test_search_preserves_diagnostics_and_passes_query_and_top_k(self):
        payload = {"query": "clock", "results": [], "request_id": "test-request", "logical_trace": [],
                   "healthy_nodes": 1, "eligible_nodes": 1, "verified_nodes": 1,
                   "node_status": [{"node_id": "node_1", "consistency": "consistent"}]}
        coordinator = Mock()
        coordinator.search.return_value = payload
        with patch.object(api_server, "coordinator", coordinator):
            result = api_server.search(api_server.SearchBody(query="  clock  ", top_k=2))
        self.assertIs(result, payload)
        coordinator.search.assert_called_once_with("clock", 2)

    def test_request_body_rejects_invalid_top_k_and_empty_query(self):
        for arguments in ({"query": ""}, {"query": "clock", "top_k": 0}, {"query": "clock", "top_k": 51}):
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                api_server.SearchBody(**arguments)

    def test_nodes_retains_configured_addresses_and_process_state(self):
        coordinator = Mock(config=CoordinatorConfig((NodeAddress("node_1", "127.0.0.1:50051"),), 1, 5, 3))
        with patch.object(api_server, "coordinator", coordinator), patch.object(api_server, "process_state", return_value="stopped"):
            result = api_server.nodes()
        self.assertEqual(result[0]["node_id"], "node_1")
        self.assertEqual(result[0]["address"], "127.0.0.1:50051")
        self.assertEqual(result[0]["state"], "stopped")

    def test_unconfigured_nodes_is_empty_and_health_is_available(self):
        with patch.object(api_server, "coordinator", None):
            self.assertEqual(api_server.nodes(), [])
        self.assertEqual(api_server.health(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
