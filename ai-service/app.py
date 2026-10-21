"""
Main Flask application for AIRS AI Service
Entry point for the multi-agent orchestration system
"""

import json
import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from config import settings
from agents.orchestrator import AIOrchestrator
from rag.retriever import RAGRetriever

# Ensure logs directory exists
os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
os.makedirs(settings.chromadb_persist_dir, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Global AI component references
orchestrator = None
rag_retriever = None


def seed_runbooks(retriever):
    """Seed initial runbooks from seed/runbooks.json into RAG knowledge base"""
    seed_path = os.path.join(os.path.dirname(__file__), "seed", "runbooks.json")
    if not os.path.exists(seed_path):
        logger.warning(f"Seed runbooks file not found at {seed_path}")
        return 0, 0
    try:
        with open(seed_path, "r", encoding="utf-8") as f:
            runbooks = json.load(f)
        if isinstance(runbooks, list) and runbooks:
            ingested, failed = retriever.ingest_documents(runbooks)
            logger.info(f"Seeded {ingested} runbooks on startup ({failed} failed)")
            return ingested, failed
        else:
            logger.warning(f"Seed runbooks file at {seed_path} is empty or not a list")
            return 0, 0
    except Exception as e:
        logger.error(f"Error seeding runbooks on startup: {e}")
        return 0, 0


def get_rag_retriever():
    """Get or lazily initialize the RAG retriever and ingest seed runbooks"""
    global rag_retriever
    if rag_retriever is None:
        rag_retriever = RAGRetriever(settings)
        logger.info("RAG retriever initialized")
        seed_runbooks(rag_retriever)
    return rag_retriever


def get_orchestrator():
    """Get or lazily initialize the AI orchestrator"""
    global orchestrator
    if orchestrator is None:
        retriever = get_rag_retriever()
        orchestrator = AIOrchestrator(settings, rag_retriever=retriever)
        logger.info("AI orchestrator lazily initialized")
    return orchestrator


def init_ai_components():
    """Eagerly initialize AI components and seed runbooks on startup"""
    get_rag_retriever()
    get_orchestrator()
    logger.info("AI components eagerly initialized")


# Initialize AI components and ingest seed runbooks on startup
try:
    init_ai_components()
except Exception as e:
    logger.warning(f"Eager initialization of AI components deferred: {e}")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "airs-ai-service"}), 200


@app.route('/api/investigate', methods=['POST'])
def investigate_incident():
    """
    Trigger multi-agent investigation for an incident
    """
    try:
        if not settings.google_api_key:
            return jsonify({
                "error": "GOOGLE_API_KEY is missing. Please set GOOGLE_API_KEY in environment variables to trigger investigation.",
                "status": "failed"
            }), 400

        data = request.get_json() or {}
        orch = get_orchestrator()
        investigation_id = orch.start_investigation(data)
        
        return jsonify({
            "investigation_id": investigation_id,
            "status": "in_progress"
        }), 202
    except Exception as e:
        logger.error(f"Investigation failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/investigate/<investigation_id>', methods=['GET'])
def get_investigation_status(investigation_id):
    """Get status of an ongoing investigation"""
    try:
        orch = get_orchestrator()
        result = orch.get_investigation_result(investigation_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Failed to retrieve investigation: {e}")
        return jsonify({"error": str(e)}), 404


@app.route('/api/rag/search', methods=['POST'])
def rag_search():
    """
    Search knowledge base using hybrid RAG (vector + lexical)
    """
    try:
        data = request.get_json() or {}
        query = data.get("query")
        top_k = data.get("top_k", 5)
        
        retriever = get_rag_retriever()
        results = retriever.hybrid_search(query, top_k)
        
        return jsonify({
            "results": results,
            "query": query,
            "count": len(results)
        }), 200
    except Exception as e:
        logger.error(f"RAG search failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/ingest', methods=['POST'])
def rag_ingest():
    """
    Ingest documents into the knowledge base
    """
    try:
        data = request.get_json() or {}
        documents = data.get("documents", [])
        
        retriever = get_rag_retriever()
        ingested, failed = retriever.ingest_documents(documents)
        
        return jsonify({
            "ingested": ingested,
            "failed": failed
        }), 200
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    try:
        init_ai_components()
        flask_host = os.environ.get("FLASK_HOST", getattr(settings, "flask_host", "127.0.0.1"))
        flask_debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "t", "yes")
        flask_port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", str(settings.flask_port))))
        logger.info(f"Starting AIRS AI Service on {flask_host}:{flask_port} (debug={flask_debug})")
        app.run(
            host=flask_host,
            port=flask_port,
            debug=flask_debug
        )
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        exit(1)
