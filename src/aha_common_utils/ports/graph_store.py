"""Generic graph query and traversal contract.

Business-independent graph operations. Domain-specific extensions (entity
linking, vector batch search, document-contribution deletion) live in the
consuming service's ``KnowledgeGraphStorePort`` subclass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from aha_common_utils.ports.types import EmbeddingVector, GraphEdge, GraphNode, JsonObject


class GraphStorePort(ABC):
    """Graph query and traversal contract."""

    @abstractmethod
    async def query(self, cypher: str, params: JsonObject | None = None) -> list[JsonObject]:
        """Execute a graph query and return rows."""

    @abstractmethod
    async def upsert_node(self, label: str, node_id: str, properties: JsonObject) -> GraphNode:
        """Create or update a graph node."""

    @abstractmethod
    async def create_edge(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: JsonObject | None = None,
    ) -> GraphEdge:
        """Create a relationship edge."""

    @abstractmethod
    async def traverse(
        self,
        node_id: str,
        rel_type: str,
        direction: str = "out",
        max_depth: int = 3,
    ) -> dict[str, list[JsonObject]]:
        """Return a small relationship subgraph."""

    @abstractmethod
    async def semantic_search(
        self,
        query_text: str,
        top_k: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[JsonObject]:
        """Search graph content semantically."""

    @abstractmethod
    async def semantic_search_vector(
        self,
        query_vector: EmbeddingVector,
        *,
        top_k: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[JsonObject]:
        """Search graph content with a caller-owned query embedding."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
