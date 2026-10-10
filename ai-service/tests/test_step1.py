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
from app import app


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


if __name__ == '__main__':
    unittest.main()
