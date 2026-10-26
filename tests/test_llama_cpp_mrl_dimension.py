"""MRL 维度裁剪：请求维度小于原生时截断并重新归一化；大于原生时拒绝。

依据：Qwen3-Embedding-4B 模型卡（huggingface.co/Qwen/Qwen3-Embedding-4B）写明
"Embedding Dimension: Up to 2560, supports user-defined output dimensions ranging
from 32 to 2560"，且 MRL Support = Yes。截断后必须重新 L2 归一化，否则余弦相似度
与未截断向量不可比。本测试不加载模型：直接调用 `_fit_dimension`，把维度行为与
模型推理解耦。
"""

from __future__ import annotations

import math

import pytest
from aha_common_utils.adapters.llama_cpp_embedding import LlamaCppEmbeddingProvider


def _provider(dimension: int) -> LlamaCppEmbeddingProvider:
    return LlamaCppEmbeddingProvider(model_path="/nonexistent.gguf", embedding_dimension=dimension)


def test_truncation_keeps_prefix_and_renormalizes() -> None:
    vector = [3.0, 4.0, 12.0, 84.0]
    out = _provider(2)._fit_dimension(vector)

    assert out == pytest.approx([0.6, 0.8])  # 3-4-5 三角形：前缀归一化
    assert math.isclose(math.sqrt(sum(v * v for v in out)), 1.0, rel_tol=1e-9)


def test_native_dimension_is_returned_unchanged() -> None:
    vector = [0.1, 0.2, 0.3]
    assert _provider(3)._fit_dimension(vector) is vector


def test_larger_than_native_is_rejected_not_padded() -> None:
    with pytest.raises(ValueError, match="exceeds the model's native dimension"):
        _provider(1024)._fit_dimension([0.1] * 8)


def test_zero_prefix_does_not_divide_by_zero() -> None:
    assert _provider(2)._fit_dimension([0.0, 0.0, 5.0]) == [0.0, 0.0]


def test_default_dimension_is_2560() -> None:
    """默认必须等于原生维度：换个模型而忘记改配置时，不该静默截断。"""
    assert LlamaCppEmbeddingProvider(model_path="/nonexistent.gguf")._embedding_dimension == 2560
