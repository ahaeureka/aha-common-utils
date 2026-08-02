"""Tests for RerankProviderPort, remote adapter, local GGUF skeleton, and typed registry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from aha_common_utils.adapters.llama_cpp_rerank import LlamaCppRerankProvider
from aha_common_utils.adapters.remote_openai_rerank import RemoteOpenAIRerankProvider
from aha_common_utils.ports.rerank_provider import RerankProviderPort, RerankScore
from aha_common_utils.rerank.provider_registry import (
    RerankProviderConfig,
    create_rerank_provider,
)


@dataclass
class _FakeResponse:
    status_code: int = 200
    _json: object = None

    def json(self) -> object:
        return self._json


@dataclass
class _FakePostClient:
    captures: list[tuple[str, dict[str, object], dict[str, object]]] | None = None

    async def post(
        self,
        url: str,
        *,
        data: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        if self.captures is not None:
            self.captures.append((url, data or {}, json or {}))
        return _FakeResponse(status_code=200, _json={"results": [{"index": 1, "relevance_score": 0.9}]})


def test_rerank_score_is_frozen_dataclass() -> None:
    score = RerankScore(index=2, score=0.75)
    assert score.index == 2
    assert score.score == 0.75


def test_remote_adapter_implements_port() -> None:
    provider = RemoteOpenAIRerankProvider(api_url="http://localhost:4000/v1", api_key="k", model="m")
    assert isinstance(provider, RerankProviderPort)


def test_remote_adapter_posts_to_rerank_endpoint() -> None:
    client = _FakePostClient(captures=[])
    provider = RemoteOpenAIRerankProvider(
        api_url="http://localhost:4000/v1",
        api_key="sk-test",
        model="qwen3-reranker",
        http_client=client,
    )

    scores = asyncio.run(provider.rerank(query="q", documents=["a", "b"], top_k=1))

    assert len(client.captures) == 1
    url, data, json_body = client.captures[0]
    assert url == "http://localhost:4000/v1/rerank"
    assert json_body["model"] == "qwen3-reranker"
    assert json_body["query"] == "q"
    assert json_body["documents"] == ["a", "b"]
    assert json_body["top_n"] == 1
    assert scores == [RerankScore(index=1, score=0.9)]


def test_remote_adapter_requires_credentials() -> None:
    with pytest.raises(ValueError, match="api_url"):
        RemoteOpenAIRerankProvider(api_url="", api_key="k", model="m")


def test_llama_cpp_provider_is_skeleton_with_pooling_type_rank() -> None:
    provider = LlamaCppRerankProvider(model_path="/app/.models/rerank.gguf")
    assert isinstance(provider, RerankProviderPort)
    assert provider._model_path == "/app/.models/rerank.gguf"
    assert provider._pooling_type_name == "RANK"


def test_llama_cpp_provider_requires_model_path() -> None:
    with pytest.raises(ValueError, match="model_path"):
        LlamaCppRerankProvider(model_path="")


def test_create_rerank_provider_builds_remote_adapter() -> None:
    provider = create_rerank_provider(
        RerankProviderConfig(
            provider="remote-openai-rerank",
            api_url="http://localhost:4000/v1",
            api_key="sk-test",
            model="qwen3-reranker",
        )
    )
    assert isinstance(provider, RemoteOpenAIRerankProvider)


def test_create_rerank_provider_builds_llama_cpp() -> None:
    provider = create_rerank_provider(
        RerankProviderConfig(provider="llama-cpp-rerank", model_path="/app/.models/rerank.gguf")
    )
    assert isinstance(provider, LlamaCppRerankProvider)


def test_create_rerank_provider_unknown_raises() -> None:
    with pytest.raises(ValueError, match="no-such"):
        create_rerank_provider(RerankProviderConfig(provider="no-such"))
