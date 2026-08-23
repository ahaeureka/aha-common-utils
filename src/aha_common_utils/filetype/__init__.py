"""分层文件类型检测器。

两层互补策略（快 → 准）：

1. **libmagic magic header**（``python-magic``）— 读文件头即可判定结构化/
   二进制类型（PDF/PNG/MP4/ZIP…），极快且确定；
2. **Magika 内容识别**（Google ML 模型）— 当第一层判定为文本或无法确定时，
   用内容级模型细分 txt/markdown/html/json/代码等。

公共 API::

    from aha_common_utils.filetype import detect_file_type, detect_mime_type

    det = detect_file_type("report.pdf")   # -> FileTypeDetection(mime="application/pdf", source="libmagic")
    det = detect_file_type("notes.md")     # -> FileTypeDetection(mime="text/plain", label="md"? , source="magika")

本模块保持业务无关：不做任何业务枚举映射，消费方按需自行映射。
"""

from __future__ import annotations

from aha_common_utils.filetype.detector import (
    FileDetector,
    FileTypeDetection,
    LayeredFileTypeDetector,
    detect_file_type,
    detect_mime_type,
    get_default_detector,
    reset_default_detector,
)

__all__ = [
    "FileDetector",
    "FileTypeDetection",
    "LayeredFileTypeDetector",
    "detect_file_type",
    "detect_mime_type",
    "get_default_detector",
    "reset_default_detector",
]
