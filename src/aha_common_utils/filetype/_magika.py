"""Magika 内容识别（分层第二级，Google ML 模型）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from aha_common_utils.filetype.types import FileTypeDetection
from aha_common_utils.logging import get_logger

if TYPE_CHECKING:
    from magika import Magika

logger = get_logger(__name__)

_magika_singleton: Magika | None = None
_magika_failed = False


def _get_magika() -> Magika | None:
    """惰性加载 Magika 单例（模型初始化开销大，避免 import 副作用）。"""
    global _magika_singleton, _magika_failed
    if _magika_singleton is not None:
        return _magika_singleton
    if _magika_failed:
        return None
    try:
        from magika import Magika

        _magika_singleton = cast("Magika", Magika())
        return _magika_singleton
    except Exception as exc:  # noqa: BLE001 - onnxruntime 缺失等环境问题
        logger.debug("Magika unavailable, layered detector will skip content layer: {}", exc)
        _magika_failed = True
        return None


class MagikaDetector:
    """基于 Magika 的内容级类型检测器。

    使用 ``MagikaResult.output``（经后处理覆写的最终判定）而非 ``dl``
    原始预测；短样本低置信度时 output 会回退到更保守的通用类型。
    """

    source = "magika"

    def detect(self, data: bytes) -> FileTypeDetection | None:
        """返回 Magika 判定；模型不可用时返回 None。"""
        model = _get_magika()
        if model is None:
            return None
        try:
            result = model.identify_bytes(data)
            info = result.output
        except Exception as exc:  # noqa: BLE001 - 防御：模型推理异常不阻断上层兜底
            logger.debug("Magika identify_bytes failed: {}", exc)
            return None
        return FileTypeDetection(
            mime=info.mime_type,
            label=info.label,
            extensions=tuple(info.extensions),
            source=self.source,
            score=float(result.score),
        )


__all__ = ["MagikaDetector"]
