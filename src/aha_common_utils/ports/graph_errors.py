"""Graph store error hierarchy."""

from __future__ import annotations


class GraphError(Exception):
    """Base exception for all graph-store errors."""


class GraphNotFoundError(GraphError):
    """Graph or node does not exist."""


class GraphUnavailableError(GraphError):
    """Graph store is unreachable or timed out."""


class GraphQueryError(GraphError):
    """Cypher syntax or execution error."""


class GraphIntegrityError(GraphError):
    """Vector index missing or corrupted."""
