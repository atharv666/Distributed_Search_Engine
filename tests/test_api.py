"""Route-level API checks without introducing an HTTP client dependency."""

import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from coordinator import api_server
from coordinator.engine.config import CoordinatorConfig, NodeAddress


class ApiTests(unittest.TestCase):
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
