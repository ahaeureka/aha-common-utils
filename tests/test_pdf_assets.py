"""AC-3(M3): aha_common_utils.pdf.assets 资产渲染与提取。

收编 k2skills pdf_source.py：_render_table_to_csv / _extract_page_images /
_image_extension / 资产预算常量（_MAX_ASSET_BYTES / _MAX_ASSETS_PER_SECTION）。
行为与收编前完全一致。
"""

from __future__ import annotations

from pathlib import Path

from aha_common_utils.pdf.assets import (
    AssetBudget,
    extract_page_images,
    image_extension,
    render_table_to_csv,
)


def _write_minimal_pdf(path: Path, text: str) -> None:
    """生成 pypdf 可读的最小单页 PDF。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_render_table_to_csv_pipe() -> None:
    para = "| 名称 | 数量 |\n| --- | --- |\n| 苹果 | 3 |"
    out = render_table_to_csv(para)
    assert out is not None
    assert out.decode("utf-8") == "名称,数量\n苹果,3\n"


def test_render_table_to_csv_tsv() -> None:
    para = "a\tb\n1\t2"
    out = render_table_to_csv(para)
    assert out is not None
    assert out.decode("utf-8") == "a,b\n1,2\n"


def test_render_table_to_csv_separator_row_filtered() -> None:
    """C9: markdown 分隔行（全 -/:）不当数据行。"""
    para = "| a | b |\n| --- | --- |\n| 1 | 2 |"
    out = render_table_to_csv(para)
    assert out is not None
    assert "---" not in out.decode("utf-8")
    assert out.decode("utf-8") == "a,b\n1,2\n"


def test_render_table_to_csv_empty_input_none() -> None:
    # 与原 _render_table_to_csv 一致：无内容行 → None
    assert render_table_to_csv("") is None
    assert render_table_to_csv("\n\n  \n") is None


def test_image_extension_magic_bytes() -> None:
    assert image_extension(b"\xff\xd8\xff") == "jpg"
    assert image_extension(b"\x89PNG\r\n\x1a\n") == "png"
    assert image_extension(b"GIF8") == "gif"
    assert image_extension(b"BM") == "bmp"
    assert image_extension(b"\x00\x01\x02") == "png"  # 兜底


def test_extract_page_images_no_images(tmp_path: Path) -> None:
    pdf = tmp_path / "plain.pdf"
    _write_minimal_pdf(pdf, "no images")
    assert extract_page_images(str(pdf), 1) == []


def test_extract_page_images_out_of_range(tmp_path: Path) -> None:
    pdf = tmp_path / "plain.pdf"
    _write_minimal_pdf(pdf, "x")
    assert extract_page_images(str(pdf), 99) == []  # 越界 → 空，不报错


def test_extract_page_images_missing_file() -> None:
    assert extract_page_images("/nonexistent/file.pdf", 1) == []  # 失败 → 空


def test_asset_budget_defaults() -> None:
    b = AssetBudget()
    assert b.max_asset_bytes == 1_048_576
    assert b.max_assets_per_section == 8


def test_asset_budget_custom() -> None:
    b = AssetBudget(max_asset_bytes=100, max_assets_per_section=3)
    assert b.would_exceed(data=b"x" * 101)
    assert not b.would_exceed(data=b"x" * 99)