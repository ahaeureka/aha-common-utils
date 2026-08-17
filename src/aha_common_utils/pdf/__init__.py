"""PDF 公共处理能力（pdf-foundation.md）。"""

from aha_common_utils.pdf.assets import (
    ASSET_REF_PREFIX,
    MAX_ASSET_BYTES,
    MAX_ASSETS_PER_SECTION,
    AssetBudget,
    extract_page_images,
    image_extension,
    render_table_to_csv,
)
from aha_common_utils.pdf.boundary import (
    PageProbe,
    apply_zones,
    resolve_front_matter_boundary,
)
from aha_common_utils.pdf.heuristics import (
    HeuristicsConfig,
    is_colophon_page,
    is_copyright_page,
    roman_numeral,
    roman_pages,
)
from aha_common_utils.pdf.layout import (
    block_kind_for_ocr_label,
    classify_ocr_blocks,
)
from aha_common_utils.pdf.ocr_channel import (
    OcrChannel,
    OcrChannelConfig,
    empty_pages,
)
from aha_common_utils.pdf.pipeline import PdfPipeline, PdfPipelineConfig
from aha_common_utils.pdf.policy import (
    apply_zone_action,
    effective_strategy,
    should_apply_boundary,
)
from aha_common_utils.pdf.segments import (
    detect_table,
    heading_or_none,
    pdf_heading_level,
    split_paragraphs,
)
from aha_common_utils.pdf.structural import (
    extract_structural_signal,
    first_chapter_page,
    outline_items,
    page_labels_from_reader,
)
from aha_common_utils.pdf.structurer import (
    SectionAccumulator,
    accumulate_sections,
)
from aha_common_utils.pdf.textlayer import (
    PageText,
    PdfTextExtractor,
    pypdf_text_extract,
)
from aha_common_utils.pdf.types import (
    FrontMatterDecision,
    FrontMatterPolicy,
    PdfAsset,
    PdfBlock,
    PdfBlockKind,
    PdfDocument,
    PdfPage,
    PdfSection,
    PdfStructuralSignal,
    PdfZone,
)

__all__ = [
    # textlayer
    "PageText",
    "PdfPipeline",
    "PdfPipelineConfig",
    "PdfTextExtractor",
    "pypdf_text_extract",
    # types
    "PdfBlockKind",
    "PdfZone",
    "PdfAsset",
    "PdfBlock",
    "PdfPage",
    "PdfSection",
    "PdfStructuralSignal",
    "PdfDocument",
    "FrontMatterDecision",
    "FrontMatterPolicy",
    # segments
    "split_paragraphs",
    "pdf_heading_level",
    "detect_table",
    "heading_or_none",
    # assets
    "AssetBudget",
    "MAX_ASSET_BYTES",
    "MAX_ASSETS_PER_SECTION",
    "ASSET_REF_PREFIX",
    "render_table_to_csv",
    "image_extension",
    "extract_page_images",
    # ocr_channel
    "OcrChannel",
    "OcrChannelConfig",
    "empty_pages",
    # boundary / heuristics / policy
    "PageProbe",
    "apply_zones",
    "resolve_front_matter_boundary",
    "HeuristicsConfig",
    "is_colophon_page",
    "is_copyright_page",
    "roman_numeral",
    "roman_pages",
    "apply_zone_action",
    "effective_strategy",
    "should_apply_boundary",
    # structurer
    "SectionAccumulator",
    "accumulate_sections",
    # structural
    "extract_structural_signal",
    "first_chapter_page",
    "outline_items",
    "page_labels_from_reader",
    # layout
    "block_kind_for_ocr_label",
    "classify_ocr_blocks",
]