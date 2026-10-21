"""
Hybrid RAG retriever combining vector and lexical search
Integrates ChromaDB (vector) and rank_bm25 (in-process BM25 lexical search)
"""

import logging
import re
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi

try:
    import chromadb
except ImportError:
    chromadb = None

logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> List[str]:
    """Tokenize text by lowercasing and splitting on non-alphanumeric characters"""
    if not text:
        return []
    return re.findall(r'\w+', text.lower())


class RAGRetriever:
    """Hybrid RAG retriever for knowledge base search using ChromaDB and BM25"""
    
    def __init__(self, settings):
        """Initialize vector and lexical search backends"""
        self.settings = settings
        self.documents: List[Dict[str, Any]] = []
        self.bm25: BM25Okapi = None
        
        # Initialize ChromaDB (vector store)
        self.vector_collection = None
        if chromadb:
            try:
                self.chroma_client = chromadb.PersistentClient(path=settings.chromadb_persist_dir)
                self.vector_collection = self.chroma_client.get_or_create_collection(
                    name="sherlog_knowledge_base"
                )
                logger.info("ChromaDB persistent client initialized")
            except Exception as e:
                logger.warning(f"ChromaDB PersistentClient fallback: {e}")
                try:
                    self.chroma_client = chromadb.Client()
                    self.vector_collection = self.chroma_client.get_or_create_collection(
                        name="sherlog_knowledge_base"
                    )
                except Exception as inner_e:
                    logger.error(f"ChromaDB failed completely: {inner_e}")
                    self.vector_collection = None

        logger.info("BM25 in-process retriever initialized")
    
    def hybrid_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining lexical (BM25) and vector (ChromaDB) results
        """
        lexical_results = []
        vector_results_list = []
        
        # 1. Lexical search (BM25Okapi)
        tokenized_query = tokenize_text(query)
        if self.bm25 and self.documents and tokenized_query:
            try:
                query_set = set(tokenized_query)
                scores = self.bm25.get_scores(tokenized_query)
                
                scored_docs = []
                for idx, score in enumerate(scores):
                    doc_tokens = set(self.documents[idx].get('tokens', []))
                    if query_set.intersection(doc_tokens) and score > 0:
                        scored_docs.append((score, self.documents[idx]))
                
                # Sort BM25 results by score descending
                scored_docs.sort(key=lambda x: x[0], reverse=True)
                
                for score, doc in scored_docs[:top_k]:
                    lexical_results.append({
                        "id": doc["id"],
                        "title": doc.get("title") or doc.get("metadata", {}).get("title", ""),
                        "content": doc["content"],
                        "score": float(score),
                        "source": "lexical_bm25",
                        "metadata": doc.get("metadata", {})
                    })
            except Exception as e:
                logger.error(f"BM25 search failed: {e}")
        
        # 2. Vector search (ChromaDB)
        if self.vector_collection:
            try:
                vector_query_res = self.vector_collection.query(
                    query_texts=[query],
                    n_results=top_k
                )
                
                if vector_query_res and vector_query_res.get('ids') and vector_query_res['ids']:
                    for i, doc_id in enumerate(vector_query_res['ids'][0]):
                        metadata = {}
                        if vector_query_res.get('metadatas') and vector_query_res['metadatas']:
                            metadata = vector_query_res['metadatas'][0][i] or {}
                        
                        # ChromaDB returns distance (lower distance = higher similarity)
                        distance = float(vector_query_res['distances'][0][i])
                        vector_results_list.append({
                            "id": doc_id,
                            "title": metadata.get("title", ""),
                            "content": vector_query_res['documents'][0][i],
                            "score": distance,
                            "source": "vector",
                            "metadata": metadata
                        })
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
        
        # Merge lexical and vector results (lexical exact matches first, then vector)
        seen_ids = set()
        deduplicated = []
        
        for doc in lexical_results:
            if doc['id'] not in seen_ids:
                seen_ids.add(doc['id'])
                deduplicated.append(doc)
                
        for doc in vector_results_list:
            if doc['id'] not in seen_ids:
                seen_ids.add(doc['id'])
                deduplicated.append(doc)
        
        return deduplicated[:top_k]
    
    def ingest_documents(self, documents: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Ingest documents into knowledge base (ChromaDB + BM25)
        """
        ingested = 0
        failed = 0
        
        for doc in documents:
            try:
                doc_id = doc.get('id')
                content = doc.get('content', '')
                source = doc.get('source', 'unknown')
                metadata = dict(doc.get('metadata', {}))
                title = doc.get('title', '')
                if title and 'title' not in metadata:
                    metadata['title'] = title
                if source and 'source' not in metadata:
                    metadata['source'] = source
                
                # Ingest into ChromaDB (vector store)
                if self.vector_collection:
                    if hasattr(self.vector_collection, 'upsert'):
                        self.vector_collection.upsert(
                            ids=[doc_id],
                            documents=[content],
                            metadatas=[metadata]
                        )
                    else:
                        self.vector_collection.add(
                            ids=[doc_id],
                            documents=[content],
                            metadatas=[metadata]
                        )
                
                # Ingest into in-process BM25 document store using regex tokenizer
                tokens = tokenize_text(content)
                if title:
                    tokens.extend(tokenize_text(title))

                doc_obj = {
                    "id": doc_id,
                    "title": title,
                    "content": content,
                    "source": source,
                    "metadata": metadata,
                    "tokens": tokens
                }

                existing_idx = next((i for i, d in enumerate(self.documents) if d['id'] == doc_id), None)
                if existing_idx is not None:
                    self.documents[existing_idx] = doc_obj
                else:
                    self.documents.append(doc_obj)

                ingested += 1
                logger.debug(f"Ingested document: {doc_id}")
            except Exception as e:
                failed += 1
                logger.error(f"Failed to ingest document {doc.get('id')}: {e}")
        
        # Rebuild BM25 index with all documents
        if self.documents:
            corpus = [d['tokens'] for d in self.documents]
            self.bm25 = BM25Okapi(corpus)
        
        logger.info(f"Ingestion complete: {ingested} succeeded, {failed} failed")
        return ingested, failed
