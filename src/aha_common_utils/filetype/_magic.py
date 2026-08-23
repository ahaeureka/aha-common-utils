"""libmagic 魔数头检测（分层第一级，python-magic 绑定）。"""

from __future__ import annotations

from aha_common_utils.filetype.types import FileTypeDetection
from aha_common_utils.logging import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - 环境相关分支
    import magic as _magic
except (ImportError, OSError) as exc:  # 缺系统 libmagic 共享库时 python-magic 会抛 OSError
    _magic = None
    logger.debug("python-magic unavailable, layered detector will skip libmagic layer: {}", exc)


class LibmagicDetector:
    """基于 libmagic 的魔数头检测器。

    只读缓冲区头部即可判定；对结构化/二进制类型几乎无误报。
    """

    source = "libmagic"

    def detect(self, data: bytes) -> FileTypeDetection | None:
        """返回 magic header 判定；库不可用或结果为空时返回 None。"""
        if _magic is None:
            return None
        try:
            mime = _magic.from_buffer(data, mime=True)
        except Exception as exc:  # noqa: BLE001 - libmagic 对畸形输入可能抛任意异常
            logger.debug("libmagic from_buffer failed: {}", exc)
            return None
        if not mime:
            return None
        return FileTypeDetection(mime=mime, label="", extensions=(), source=self.source, score=None)


__all__ = ["LibmagicDetector"]
