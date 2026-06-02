"""Semantic Memory - Embeddings, Chroma integration"""
import chromadb
from typing import List, Dict, Any

from core.logging_setup import get_logger

log = get_logger(__name__)

class SemanticMemory:
    def __init__(self, config=None):
        self.config = config or {}
        db_path = self.config.get("db_path", "./semantic_db")
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="jarvis_memory")
        log.info(f"Zainicjalizowano Semantic Memory w: {db_path}")
    
    def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any] = None):
        """Dodaje lub aktualizuje dokument w bazie wektorowej."""
        try:
            self.collection.add(
                documents=[content],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
            log.info(f"Opublikowano do semantic memory: {doc_id}")
            return True
        except Exception as e:
            log.error(f"Błąd indeksowania: {e}")
            return False
            
    def update_document(self, doc_id: str, content: str, metadata: Dict[str, Any] = None):
        try:
            self.collection.update(
                documents=[content],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
            log.info(f"Zaktualizowano w semantic memory: {doc_id}")
            return True
        except Exception as e:
            log.error(f"Błąd aktualizacji doc {doc_id}: {e}")
            return False
            
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Zwraca najlepiej dopasowane wektory dla query."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k
            )
            
            output = []
            if results and results.get("documents") and len(results["documents"]) > 0:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
                
                for i in range(len(docs)):
                    output.append({
                        "id": ids[i],
                        "content": docs[i],
                        "metadata": metas[i]
                    })
            return output
        except Exception as e:
            log.error(f"Błąd wyszukiwania semantycznego dla '{query}': {e}")
            return []

