import asyncio
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    Distance,
    MatchAny
)
from sentence_transformers import SentenceTransformer
from app.logger import get_logger
import uuid

logger = get_logger(__name__)

# Model lazy loading - avoid blocking on import
_encoder = None
_encoder_lock = asyncio.Lock()

# Constants
MIN_TEXT_LENGTH = 2
DEFAULT_VECTOR_DIMENSIONS = 384
DEFAULT_SIMILARITY_THRESHOLD = 0


async def get_encoder(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> SentenceTransformer:
    """
    Get or load the sentence transformer model (lazy loading).
    This avoids blocking the application startup.

    Args:
        model_name: HuggingFace model name

    Returns:
        SentenceTransformer instance

    Raises:
        RuntimeError: If model loading fails
    """
    global _encoder

    if _encoder is not None:
        return _encoder

    async with _encoder_lock:
        if _encoder is not None:
            return _encoder

        try:
            logger.info(
                "Loading sentence transformer model",
                extra={"event_type": "model_load_start", "model": model_name},
            )
            _encoder = SentenceTransformer(model_name, device="cpu")
            logger.info(
                "Sentence transformer model loaded successfully",
                extra={"event_type": "model_load_success"},
            )
            return _encoder
        except Exception as e:
            logger.error(
                "Failed to load sentence transformer model",
                extra={"event_type": "model_load_error", "error": str(e)},
                exc_info=True,
            )
            raise RuntimeError(f"Failed to load encoder model: {str(e)}")


class VectorStore:
    """Vector store for semantic search supporting Text2SQL optimization"""

    def __init__(self, client: AsyncQdrantClient):
        """
        Initialize vector store.

        Args:
            client: Qdrant AsyncQdrantClient instance
        """
        self.collection_name: Optional[str] = None
        self.client = client

    async def list_collections(self) -> Any:
        """
        List all collections in vector database.

        Returns:
            Collections list
        """
        try:
            all_collections = await self.client.get_collections()
            logger.debug("Collections listed", extra={"event_type": "collections_listed"})
            return all_collections
        except Exception as e:
            logger.error(
                "Failed to list collections",
                extra={"event_type": "list_collections_error", "error": str(e)},
                exc_info=True,
            )
            raise

    async def ensure_collection(
        self,
        collection_name: str,
        similarity_metric: str = "cosine",
        vector_dimensions: int = DEFAULT_VECTOR_DIMENSIONS,
    ) -> tuple[Any, str]:
        """
        Create or get existing collection.

        Args:
            collection_name: Name of the collection
            similarity_metric: Similarity metric (cosine, euclidean, dot)
            vector_dimensions: Vector embedding dimensions (default: 384)

        Returns:
            Tuple of (collection_details, status_message)

        Raises:
            Exception: If collection creation fails
        """
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        try:
            # Map similarity metric to Qdrant distance metric
            metric_map = {
                "cosine": Distance.COSINE,
                "euclidean": Distance.EUCLID,
                "dot": Distance.DOT,
            }
            distance_metric = metric_map.get(similarity_metric.lower(), Distance.COSINE)

            self.collection_name = collection_name
            collection_exists = await self.client.collection_exists(collection_name)

            if not collection_exists:
                await self.client.create_collection(
                    self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_dimensions, distance=distance_metric
                    ),
                )
                status = "Collection created"
                logger.info(
                    "Vector collection created",
                    extra={
                        "event_type": "collection_created",
                        "collection": collection_name,
                    },
                )
            else:
                status = "Collection already exists"
                logger.debug(
                    "Collection already exists",
                    extra={"event_type": "collection_exists", "collection": collection_name},
                )

            collection_details = await self.client.get_collection(self.collection_name)
            return collection_details, status

        except Exception as e:
            logger.error(
                "Failed to ensure collection",
                extra={
                    "event_type": "ensure_collection_error",
                    "collection": collection_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def get_collection_details(self, collection_name: str) -> Any:
        """
        Get collection details.

        Args:
            collection_name: Name of the collection

        Returns:
            Collection details

        Raises:
            Exception: If retrieval fails
        """
        try:
            details = await self.client.get_collection(collection_name)
            logger.debug(
                "Collection details retrieved",
                extra={"event_type": "collection_details_retrieved", "collection": collection_name},
            )
            return details
        except Exception as e:
            logger.error(
                "Failed to get collection details",
                extra={
                    "event_type": "get_collection_details_error",
                    "collection": collection_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def delete_collection(self, collection_name: str) -> None:
        """
        Delete a collection.

        Args:
            collection_name: Name of the collection to delete

        Raises:
            Exception: If deletion fails
        """
        try:
            await self.client.delete_collection(collection_name)
            logger.info(
                "Collection deleted",
                extra={"event_type": "collection_deleted", "collection": collection_name},
            )
        except Exception as e:
            logger.error(
                "Failed to delete collection",
                extra={
                    "event_type": "delete_collection_error",
                    "collection": collection_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def delete_vectors_by_context_type(self, context_type: str, other_condition: dict | None = None) -> None:
        """
        Delete vectors by context type.

        Args:
            context_type: Context type label to filter deletions

        Raises:
            Exception: If deletion fails
        """
        try:
            points_selector = Filter(must=[FieldCondition(key="context_type", match=MatchValue(value=context_type))])
            if other_condition:
                for key, value in other_condition.items():
                    points_selector.must.append(FieldCondition(key=key, match=MatchValue(value=value)))

            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=points_selector,
            )
            logger.info(
                "Vectors deleted by context type",
                extra={
                    "event_type": "vectors_deleted_by_context",
                    "collection": self.collection_name,
                    "context_type": context_type,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to delete vectors by context type",
                extra={
                    "event_type": "delete_vectors_by_context_error",
                    "collection": self.collection_name,
                    "context_type": context_type,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts to vectors.

        Args:
            texts: List of text strings

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts is empty
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        try:
            encoder = await get_encoder()
            embeddings = encoder.encode(texts).tolist()
            logger.debug(
                "Texts embedded",
                extra={
                    "event_type": "texts_embedded",
                    "count": len(embeddings),
                    "dimension": len(embeddings[0]) if embeddings else 0,
                },
            )
            return embeddings
        except Exception as e:
            logger.error(
                "Failed to embed texts",
                extra={"event_type": "embed_texts_error", "count": len(texts), "error": str(e)},
                exc_info=True,
            )
            raise

    async def embed_text(self, text: str) -> List[float]:
        """
        Embed single text to vector.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector

        Raises:
            ValueError: If text is empty
        """
        if not text or not isinstance(text, str):
            raise ValueError("text must be a non-empty string")

        try:
            encoder = await get_encoder()
            embedding = encoder.encode(text).tolist()
            return embedding
        except Exception as e:
            logger.error(
                "Failed to embed text",
                extra={"event_type": "embed_text_error", "error": str(e)},
                exc_info=True,
            )
            raise

    async def upsert_data_points(self, documents: List[str], metadata: List[Dict[str, Any]], context_type: str) -> bool:
        """
        Upsert generic data points with embeddings.

        Args:
            documents: List of text documents to embed
            metadata: List of dicts with metadata corresponding to each document
            context_type: Context type label for filtering

        Returns:
            True if successful

        Raises:
            Exception: If upsert fails
        """
        if not documents or not metadata or len(documents) != len(metadata):
            raise ValueError("documents and metadata must be non-empty lists of the same length")

        try:
            embeddings = await self.embed_texts(documents)

            points = []
            for embedding, meta in zip(embeddings, metadata):
                payload = {**meta, "context_type": context_type}
                points.append(PointStruct(id=str(uuid.uuid4()), vector=embedding, payload=payload))

            await self.client.upsert(collection_name=self.collection_name, points=points)

            logger.info(
                "Data points upserted",
                extra={
                    "event_type": "data_points_upserted",
                    "count": len(points),
                    "context_type": context_type,
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to upsert data points",
                extra={
                    "event_type": "upsert_data_points_error",
                    "count": len(documents),
                    "context_type": context_type,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise


    async def _query_data(
        self, 
        user_query: str,
        must_filters: Optional[Dict[str, Any]] = None,
        should_filters: Optional[Dict[str, Any]] = None,
        n_results: int = 5,
        score_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Internal method to query data with flexible filters.
        Args:
            must_filters: Dict of key-value pairs for must conditions
            should_filters: Dict of key-value pairs for should conditions
            user_query: User's natural language query
            n_results: Number of results to return (default: 5)
            score_threshold: Minimum similarity score threshold

        Returns:
            List of matching results with payload and scores
        Raises:
            Exception: If query fails
        """
        if not user_query:
            raise ValueError("user_query cannot be empty")

        try:
            embedding = await self.embed_text(user_query)
            
            must_conditions = []
            for k, v in (must_filters or {}).items():
                if isinstance(v, list):
                    must_conditions.append(FieldCondition(key=k, match=MatchAny(any=v)))
                else:
                    must_conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            
            should_conditions = []
            for k, v in (should_filters or {}).items():
                if isinstance(v, list):
                    should_conditions.append(FieldCondition(key=k, match=MatchAny(any=v)))
                else:
                    should_conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=n_results,
                with_payload=True,
                query_filter=Filter(must=must_conditions, should=should_conditions),
            )

            # Filter by score threshold
            filtered_results = [
                {"payload": result.payload, "score": result.score}
                for result in results.points
                if result.score >= score_threshold
            ]

            logger.info(
                "Sample queries retrieved",
                extra={
                    "event_type": "sample_queries_retrieved",
                    "query": user_query,
                    "results_count": len(filtered_results),
                },
            )
            return filtered_results
        except Exception as e:
            logger.error(
                "Failed to query data",
                extra={
                    "event_type": "query_data_error",
                    "query": user_query,
                    "must": must_filters,
                    "should": should_filters,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
