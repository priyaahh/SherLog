"""
Verification tests for Step 1: SherLog ai-service setup
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add ai-service root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import settings
from rag.retriever import RAGRetriever
from agents.orchestrator import AIOrchestrator
from app import app, get_rag_retriever


class TestStep1AIService(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_01_bm25_and_hybrid_search(self):
        """
        Test RAG retrieval with multiple documents:
        1. Exact keyword / error code match via BM25
        2. Semantic query match via vector embeddings
        """
        print("\n--- Running Test 1: Hybrid RAG Search (BM25 Lexical + Vector) ---")
        retriever = RAGRetriever(settings)
        
        sample_docs = [
            {
                "id": "rb_db_pool",
                "content": "Error code ERR_DB_POOL_EXHAUSTED: Database connection pool exhausted. Increase max_connections.",
                "source": "runbook_db",
                "metadata": {"component": "postgres", "code": "ERR_DB_POOL_EXHAUSTED"}
            },
            {
                "id": "rb_nginx_504",
                "content": "HTTP 504 Gateway Timeout on nginx ingress controller due to upstream network lag.",
                "source": "runbook_ingress",
                "metadata": {"component": "nginx"}
            },
            {
                "id": "rb_jvm_oom",
                "content": "Memory leak in Java JVM heap causing OutOfMemoryError in auth worker pods.",
                "source": "runbook_jvm",
                "metadata": {"component": "jvm"}
            },
            {
                "id": "rb_kafka_lag",
                "content": "Kafka consumer lag exceeding threshold on payment-events stream.",
                "source": "runbook_kafka",
                "metadata": {"component": "kafka"}
            },
            {
                "id": "rb_ssl_cert",
                "content": "TLS/SSL certificate expired on api gateway ingress termination endpoint.",
                "source": "runbook_ssl",
                "metadata": {"component": "security"}
            }
        ]
        
        ingested, failed = retriever.ingest_documents(sample_docs)
        self.assertEqual(ingested, len(sample_docs))
        self.assertEqual(failed, 0)
        
        # 1. Lexical BM25 exact error code match
        exact_code = "ERR_DB_POOL_EXHAUSTED"
        lexical_results = retriever.hybrid_search(exact_code, top_k=3)
        print(f"Exact Code Query ('{exact_code}') -> Top Match ID: {lexical_results[0]['id']}")
        
        self.assertGreaterEqual(len(lexical_results), 1)
        self.assertEqual(lexical_results[0]['id'], "rb_db_pool")
        
        # Verify that BM25 scored this document
        bm25_tokens = exact_code.lower().split()
        bm25_scores = retriever.bm25.get_scores(bm25_tokens)
        db_doc_index = [d['id'] for d in retriever.documents].index("rb_db_pool")
        self.assertGreater(bm25_scores[db_doc_index], 0)
        print(f"BM25 Score for target document: {bm25_scores[db_doc_index]:.4f}")
        
        # 2. Semantic query match (different wording, same concept)
        semantic_query = "database running out of client connections"
        semantic_results = retriever.hybrid_search(semantic_query, top_k=3)
        result_ids = [r['id'] for r in semantic_results]
        print(f"Semantic Query ('{semantic_query}') -> Result IDs: {result_ids}")
        
        self.assertIn("rb_db_pool", result_ids)

    def test_02_health_endpoint(self):
        """Test /health endpoint returns 200 OK and healthy status"""
        print("\n--- Running Test 2: GET /health ---")
        response = self.client.get('/health')
        print(f"Status Code: {response.status_code}")
        print(f"Response JSON: {response.get_json()}")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json().get("status"), "healthy")

    def test_03_investigate_without_api_key(self):
        """Test /api/investigate returns 400 with a clear error message when GOOGLE_API_KEY is not set"""
        print("\n--- Running Test 3: POST /api/investigate (No Gemini API Key) ---")
        original_key = settings.google_api_key
        settings.google_api_key = None
        
        try:
            response = self.client.post('/api/investigate', json={
                "incident_id": "test_inc_001",
                "logs": ["2026-10-09 19:00:00 ERROR connection refused"]
            })
            print(f"Status Code: {response.status_code}")
            print(f"Response JSON: {response.get_json()}")
            
            self.assertEqual(response.status_code, 400)
            json_data = response.get_json()
            self.assertIn("error", json_data)
            self.assertIn("GOOGLE_API_KEY is missing", json_data["error"])
            self.assertEqual(json_data.get("status"), "failed")
        finally:
            settings.google_api_key = original_key

    def test_04_investigate_with_mocked_orchestrator(self):
        """Test /api/investigate returns 202 Accepted and an investigation_id when mocked (no real API call)"""
        print("\n--- Running Test 4: POST /api/investigate (Mocked Orchestrator) ---")
        original_key = settings.google_api_key
        settings.google_api_key = "mock_gemini_key_for_testing"
        
        mock_orch = MagicMock()
        mock_orch.start_investigation.return_value = "mocked-investigation-uuid-1234"
        
        try:
            with patch('app.get_orchestrator', return_value=mock_orch):
                response = self.client.post('/api/investigate', json={
                    "incident_id": "test_inc_mock",
                    "logs": ["2026-10-09 19:00:00 ERROR memory leak detected in worker"]
                })
                print(f"Status Code: {response.status_code}")
                print(f"Response JSON: {response.get_json()}")
                
                self.assertEqual(response.status_code, 202)
                json_data = response.get_json()
                self.assertEqual(json_data.get("investigation_id"), "mocked-investigation-uuid-1234")
                self.assertEqual(json_data.get("status"), "in_progress")
                mock_orch.start_investigation.assert_called_once()
        finally:
            settings.google_api_key = original_key

    def test_05_startup_seed_runbooks_ingested(self):
        """
        Test that seed runbooks from seed/runbooks.json are automatically ingested
        on app startup and available for retrieval.
        """
        print("\n--- Running Test 5: Verify Startup Seed Runbooks Ingestion ---")
        retriever = get_rag_retriever()
        
        # Verify retriever has documents loaded
        doc_ids = [d["id"] for d in retriever.documents]
        print(f"Loaded Document IDs: {doc_ids}")
        
        # Verify all 5 required error categories are covered
        required_categories = [
            ("db_pool_exhausted", "rb_db_pool_exhausted"),
            ("OOM", "rb_oom_heap_exhaustion"),
            ("request_timeout", "rb_request_timeout"),
            ("connection_failure", "rb_connection_failure"),
            ("ssl_cert", "rb_ssl_cert_expired")
        ]
        
        for cat_name, expected_id in required_categories:
            self.assertIn(
                expected_id,
                doc_ids,
                f"Expected runbook {expected_id} for {cat_name} to be ingested on startup"
            )
            
        # Verify search via /api/rag/search endpoint works for seeded runbooks
        res = self.client.post('/api/rag/search', json={
            "query": "SSL certificate expired verification failed",
            "top_k": 3
        })
        self.assertEqual(res.status_code, 200)
        search_data = res.get_json()
        result_ids = [r["id"] for r in search_data.get("results", [])]
        print(f"RAG search results for SSL query: {result_ids}")
        self.assertIn("rb_ssl_cert_expired", result_ids)
        
        # Verify search for database connection pool exhaustion
        res_db = self.client.post('/api/rag/search', json={
            "query": "ERR_DB_POOL_EXHAUSTED cannot acquire connection pool timeout",
            "top_k": 3
        })
        self.assertEqual(res_db.status_code, 200)
        db_results = [r["id"] for r in res_db.get_json().get("results", [])]
        print(f"RAG search results for DB pool query: {db_results}")
        self.assertIn("rb_db_pool_exhausted", db_results)

    def test_06_llm_retries_on_503_and_recovers(self):
        """Test LLM retries on 503 / UNAVAILABLE / 429 with backoff and succeeds on recovery"""
        print("\n--- Running Test 6: LLM Retries on 503 / UNAVAILABLE ---")
        orchestrator = AIOrchestrator(settings)
        
        mock_llm = MagicMock()
        success_response = MagicMock()
        success_response.content = "Root cause: transient upstream 503 recovered after retry."
        # Fail twice with 503 UNAVAILABLE, succeed on 3rd call
        mock_llm.invoke.side_effect = [
            Exception("503 Server Unavailable"),
            Exception("UNAVAILABLE: Service temporarily overloaded"),
            success_response
        ]
        orchestrator.llm = mock_llm
        
        state = {
            "investigation_id": "test-retry-1",
            "logs": ["2026-10-10 ERROR 503 service unavailable"],
            "anomalies": [{"type": "request_timeout", "severity": "high", "count": 1}],
            "relevant_runbooks": [],
            "errors": []
        }
        
        with patch('time.sleep') as mock_sleep:
            result_state = orchestrator._root_cause_agent(state)
            
            # Should have invoked 3 times (initial + 2 retries)
            self.assertEqual(mock_llm.invoke.call_count, 3)
            # Should have slept with backoff delays 2s, 4s
            self.assertEqual(mock_sleep.call_count, 2)
            mock_sleep.assert_has_calls([unittest.mock.call(2), unittest.mock.call(4)])
            self.assertEqual(result_state["root_cause"], "Root cause: transient upstream 503 recovered after retry.")

    def test_07_llm_retries_fail_and_uses_fallback_model(self):
        """Test that exhausting all 5 retries triggers the fallback model once"""
        print("\n--- Running Test 7: All 5 Retries Fail -> Fallback Model Invocation ---")
        orchestrator = AIOrchestrator(settings)
        orchestrator.settings.llm_fallback_model = "gemini-1.5-pro-fallback"
        
        mock_primary_llm = MagicMock()
        # Fail on initial attempt + 5 retries (6 attempts total) with 429 Resource Exhausted
        mock_primary_llm.invoke.side_effect = [
            Exception("429 Resource Exhausted: quota exceeded") for _ in range(6)
        ]
        orchestrator.llm = mock_primary_llm
        
        mock_fallback_llm = MagicMock()
        fallback_resp = MagicMock()
        fallback_resp.content = "Root cause: diagnosed by fallback model after primary 429 quota exhaustion."
        mock_fallback_llm.invoke.return_value = fallback_resp
        orchestrator.fallback_llm = mock_fallback_llm
        
        state = {
            "investigation_id": "test-fallback-1",
            "logs": ["2026-10-10 ERROR 429 quota exceeded"],
            "anomalies": [{"type": "request_timeout", "severity": "high", "count": 1}],
            "relevant_runbooks": [],
            "errors": []
        }
        
        with patch('time.sleep') as mock_sleep:
            result_state = orchestrator._root_cause_agent(state)
            
            # Primary LLM invoked 6 times (1 initial + 5 retries)
            self.assertEqual(mock_primary_llm.invoke.call_count, 6)
            # Backoff delays: 2s, 4s, 8s, 16s, 32s
            self.assertEqual(mock_sleep.call_count, 5)
            mock_sleep.assert_has_calls([
                unittest.mock.call(2),
                unittest.mock.call(4),
                unittest.mock.call(8),
                unittest.mock.call(16),
                unittest.mock.call(32)
            ])
            # Fallback LLM invoked once
            mock_fallback_llm.invoke.assert_called_once()
            self.assertEqual(
                result_state["root_cause"],
                "Root cause: diagnosed by fallback model after primary 429 quota exhaustion."
            )

    def test_08_llm_non_retryable_error_does_not_retry(self):
        """Test non-retryable error (e.g. 400 Bad Request) fails immediately without backoff"""
        print("\n--- Running Test 8: Non-retryable error does not backoff ---")
        orchestrator = AIOrchestrator(settings)
        orchestrator.settings.llm_fallback_model = ""
        
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("400 Bad Request: Invalid model argument")
        orchestrator.llm = mock_llm
        
        state = {
            "investigation_id": "test-non-retryable",
            "logs": ["2026-10-10 ERROR bad request"],
            "anomalies": [{"type": "db_pool_exhausted", "severity": "critical", "count": 1}],
            "relevant_runbooks": [],
            "errors": []
        }
        
        with patch('time.sleep') as mock_sleep:
            result_state = orchestrator._root_cause_agent(state)
            
            # Should have called primary LLM only once
            self.assertEqual(mock_llm.invoke.call_count, 1)
            # Should not sleep at all
            self.assertEqual(mock_sleep.call_count, 0)
            # Should fall back to deterministic root cause
            self.assertIn("connection pool", result_state["root_cause"].lower())


if __name__ == '__main__':
    unittest.main()
