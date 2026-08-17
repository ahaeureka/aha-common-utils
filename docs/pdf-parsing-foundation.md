# PDF 基础解析与版面分析公共能力（aha-common-utils）

> 状态：设计讨论沉淀（v0.1，草稿待评审）
> 适用范围：书籍/文档类 PDF 的基础解析（文本层 + OCR 通道 + 版面分析 + 区块结构化）
> 关联文档：`docs/pdf-frontmatter-strategy.md`（front matter 识别与分区，消费本管线输出）
> 现状宿主：`k2skills-core/domains/datasource/pdf_source.py` + `content/normalizer/books.py` + `text_html.py`
> 目标宿主：`aha-common-utils`（公共 PDF 能力下沉，业务端只消费结构化输出）

---

## 1. 背景与问题

### 1.1 现状：能力分散且重复

| 能力 | 现状位置 | 问题 |
|---|---|---|
| pypdf 文本层提取 `_pypdf_extract` | `pdf_source.py` 与 `books.py` **各一份** | 代码重复，两份实现必然漂移 |
| OCR 通道注入 | `pdf_source.py` + `aha-common-utils.ports.ocr_provider` | 端口已公共，但页面级编排在业务侧 |
| 段落拆分 `_split_paragraphs` | `content/normalizer/text_html.py` | 通用能力长在 HTML 模块里，命名误导 |
| 标题级启发式 `_pdf_heading_level` | `content/normalizer/books.py` | 通用规则混在书籍业务归一化里 |
| 表格检测/CSV 渲染 `_detect_table`/`_render_table_to_csv` | `books.py` + `pdf_source.py` | 同上 |
| 页图/表格资产提取 | `pdf_source.py._extract_page_images/_try_add_asset` | 资产容器 `SectionAsset` 是 k2skills 方言 |
| 版面分析布局标签 | `OcrLayoutBlock.label` 已公共 | label→块类型映射只在 exam-highlight 有，k2skills 未用 |

**核心问题**：通用能力与业务方言耦合——`pdf_source.py` 直接 import `books.py`/`text_html.py` 内部符号，任何一个业务项目要用 PDF 管线都只能整包搬 or 手写重造。

### 1.2 目标

1. 把 **PDF 基础解析 + 版面分析** 作为公共能力下沉 `aha-common-utils`：
   - 文本层提取（pypdf / 可注入提取器）；
   - OCR 通道编排（复用既有 `OcrProviderPort`）；
   - 版面分析（OCR 布局标签 → 通用块类型）；
   - 段落拆分 / 标题级启发式 / 表格检测与 CSV 渲染；
   - 页图与表格资产提取；
   - 结构化输出契约（业务无关的 `PdfDocument` 模型）。
2. **业务端只消费输出数据**做业务映射（endpoint IR、检索单元、编译输入……），不碰解析细节。
3. 消除 `_pypdf_extract` 等重复实现。

### 1.3 边界（非目标）

- 不做业务方言：无 k2skills proto / 表 / DTO 依赖；
- 不代行业务决策：章节如何映射为 endpoint、检索单元如何切割，由业务端基于输出契约决定；
- 版面分析只做"标签→块类型 + 层级"结构化，不做像素级 OCR 引擎（引擎走注入的 OcrProviderPort）；
- 文档本阶段只含设计，不含实现代码。

---

## 2. 能力边界划分：公共 vs 业务

### 2.1 公共（aha-common-utils.pdf）

```
输入                         公共管线（aha_common_utils/pdf）                输出（业务无关契约）
─────                        ───────────────────────────────                ──────────────────
PDF 文件 ── L0 文本层提取 ──► PdfPage{text, page_label}                ──► PdfDocument
   │         (pypdf / 注入)     │
   │                            ├─ L1 版面分析：OCR 布局标签→块类型      ──► PdfBlock{kind,
   ├─ L0b OCR 通道（空页）──►    │   （页眉/页码/标题/段落/表格/图/公式）      text, bbox,
   │         (OcrProviderPort)  ├─ L2 区块结构化：段落拆分/标题级/表格检测    level, page, meta}
   └─ L0c 资产提取（页图）──►    ├─ L3 资产渲染：表格 CSV / 页图字节
                                └─ L4 章节聚合：heading 驱动 → 通用 Section
                                                                        ──► PdfSection{
                                                                              title, zone,
                                                                              page_span,
                                                                              blocks, assets}
```

### 2.2 业务（消费端，各自项目）

| 业务端 | 消费方式（示例） |
|---|---|
| k2skills datasource | `PdfSection` → `EndpointSpec`/`SourceRef`（`pdf_sections_to_endpoints` 改写为消费公共输出） |
| k2skills content_normalizer | `PdfDocument` → `NormalizedTextUnit`（`PdfBookNormalizer` 改薄，只留映射） |
| exam-highlight（后续迁移） | `PdfBlock`/`PdfSection` → 分块/引用坐标（`CitationCoordinateRef` 式溯源） |
| 任何模板项目 | 直接消费 `PdfDocument` 做自有业务 |

---

## 3. 公共输出契约（`types.py`，业务无关）

```python
# aha_common_utils/pdf/types.py （形态示意，非最终签名）

PdfZone = Literal["front_matter", "body", "back_matter"]
PdfBlockKind = Literal[
    "heading", "paragraph", "table", "figure", "caption",
    "formula", "header", "footer", "page_number",
    "toc_content", "reference", "decorative",
]

@dataclass(frozen=True, slots=True)
class PdfBlock:
    kind: PdfBlockKind
    text: str
    page_number: int
    level: int | None = None          # heading 层级（1..N）
    bbox: list[float] = field(default_factory=list)   # 版面分析证据
    source: Literal["text", "ocr"] = "text"
    metadata: JsonObject = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class PdfPage:
    page_number: int
    text: str
    blocks: list[PdfBlock]
    page_label: str | None = None     # PageLabels 罗马/阿拉伯
    metadata: JsonObject = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class PdfSection:
    section_id: str
    title: str
    zone: PdfZone = "body"            # front matter 分区在管线内即产出
    page_start: int = 0
    page_end: int = 0
    blocks: list[PdfBlock] = field(default_factory=list)
    assets: list[PdfAsset] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class PdfAsset:
    kind: Literal["figure", "table_csv"]
    data: bytes
    ext: str
    origin: str

@dataclass(frozen=True, slots=True)
class PdfDocument:
    pages: list[PdfPage]
    sections: list[PdfSection]
    outline: JsonObject | None = None   # L0 书签树（front matter/章节树消费）
    page_labels: list[str] = field(default_factory=list)
    metadata: JsonObject = field(default_factory=dict)
```

**契约规则**：只有 `Literal`/`JsonObject`/bytes，无任何领域类型——任何项目可无痛消费。

---

## 4. 管线模块划分（`aha_common_utils/pdf/`）

沿用该包既有分层 ports → 纯逻辑 → adapters → testing：

```
aha_common_utils/pdf/
├── __init__.py
├── types.py          # §3 契约
├── textlayer.py      # L0：pypdf 文本层提取（adapter：PdfTextExtractor 协议）
├── ocr_channel.py    # L0b：空页 OCR 通道编排（复用 OcrProviderPort + 页渲染注入）
├── layout.py         # L1：OcrLayoutBlock.label → PdfBlockKind 映射 + 页眉/页码规则
├── segments.py       # L2：段落拆分（收编 _split_paragraphs）+ 标题级（收编 _pdf_heading_level）
├── assets.py         # L0c/L3：页图提取 + 表格 CSV 渲染（收编 _render_table_to_csv）
├── structurer.py     # L4：heading 驱动章节聚合 → PdfSection（兼容 legacy 平铺模式）
├── boundary.py       # front matter 边界裁决（L0-L3 信号，见 pdf-frontmatter-strategy.md）
├── policy.py         # 解析/分区策略（strategy/zone_action/语言等）
└── pipeline.py       # 主入口：PdfPipeline.parse(path) -> PdfDocument（编排 L0→L4）
```

**分层约束**（沿用 reusable-runtime-components.md）：
- `pdf/` 只依赖 stdlib + pypdf + `aha_common_utils.ports`（ocr_provider/types）；
- 不 import 任何业务包；`PdfTextExtractor`/`OcrProviderPort`/页面渲染器均为可注入协议（测试注入 fake，生产注入真实实现）；
- `structurer.py` 的章节聚合对 k2skills 现在的 `_SectionAccumulator` 逻辑是**收编而非改写**——同样的 heading 驱动逻辑，产出公共 `PdfSection`。

### 4.1 主入口 API 草案

```python
# aha_common_utils/pdf/pipeline.py（形态示意）

@dataclass(frozen=True, slots=True)
class PdfPipelineConfig:
    language: str = "Chinese"
    extract_assets: bool = True
    front_matter: str = "auto"          # auto | outline | none（见 frontmatter 文档）
    zone_action: str = "separate"       # drop | separate | keep
    page_text_extractor: PdfTextExtractor | None = None
    ocr: OcrProviderPort | None = None
    page_renderer: PageRenderer | None = None

class PdfPipeline:
    def __init__(self, config: PdfPipelineConfig) -> None: ...
    async def parse(self, path: str | Path) -> PdfDocument:
        """L0 文本层 → 空页 OCR → 版面块结构化 → 章节聚合 → front matter 分区。"""
        ...
```

---

## 5. 收编清单（迁移时消除的重复/错位）

| 现符号 | 现位置 | 去向 |
|---|---|---|
| `_pypdf_extract`（×2） | `pdf_source.py` 109 / `books.py` 58 | `textlayer.py`（单一实现） |
| `_split_paragraphs` | `text_html.py` 38 | `segments.py`（去 HTML 命名误导） |
| `_pdf_heading_level` | `books.py` 34 | `segments.py` |
| `_detect_table` | `books.py` 45 | `segments.py` |
| `_render_table_to_csv` | `pdf_source.py` 208 | `assets.py` |
| `_extract_page_images`/`_try_add_asset` | `pdf_source.py` 232/250 | `assets.py`（资产容器换 `PdfAsset`） |
| `_SectionAccumulator` | `pdf_source.py` 305 | `structurer.py`（产出 `PdfSection`） |
| OCR 通道编排 | `pdf_source.py` 287 `_ocr_page` | `ocr_channel.py` |
| label→块类型映射 | 仅 exam-highlight `layout.py` | `layout.py`（k2skills 首次受益） |

---

## 6. 落地路径（里程碑）

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 契约 + 文本层 | `types.py` + `textlayer.py`（收编两份 `_pypdf_extract`） | 两项目文本层行为一致；PDF 现有测试对拍 |
| M2 OCR 通道 + 版面 | `ocr_channel.py` + `layout.py` | 空页 OCR 恢复 + 布局标签映射单测 |
| M3 区块 + 资产 | `segments.py` + `assets.py` | 收编全部 k2skills 启发式；表格 CSV/页图输出不变 |
| M4 章节聚合 + 管线 | `structurer.py` + `pipeline.py` | `PdfPipeline.parse` 与 `PdfDocumentParser.parse` 输出对拍 |
| M5 业务迁移 | k2skills `pdf_source.py`/`books.py`/`text_html.py` 改薄为消费端映射 | k2skills 全量测试绿；业务侧删重复实现 |
| M6 front matter 集成 | `boundary.py` + `policy.py`（对接已有设计文档） | front matter 分区验收见 pdf-frontmatter-strategy.md §7-8 |

## 7. 评测与回归

- **对拍策略**：M3/M4 阶段用现有 k2skills PDF 测试作为黄金输出（sections/asset 级 diff），确保迁移零行为变化；
- **增量验证**：M6 起按 frontmatter 文档的评测集（20–30 本）验收分区质量；
- 公共包独立测试 + k2skills 全量回归双轨（沿用现有 1497 基线）。

---

## 8. 决策记录（本设计已锁定）

- **D1**：PDF 基础解析与版面分析为公共能力，下沉 `aha-common-utils.pdf`；业务端只消费 `PdfDocument` 契约（§2/§3）。
- **D2**：输出契约业务无关（Literal/JsonObject/bytes），端口注入（extractor/ocr/渲染器）保持可测（§3/§4）。
- **D3**：既有 k2skills 启发式与章节聚合全部**收编**到公共管线，迁移期输出对拍保证零行为变化（§5/§7）。
- **D4**：front matter 分区为管线内可选项（policy 控制），复用已沉淀的边界裁决设计（§4 boundary.py）。
- **待决（评审征询）**：`PdfAsset` 与 k2skills `SectionAsset` 的兼容迁移策略（字段直接迁移 vs 适配层）；`text_html.py` 收编后其业务引用是否同步改指向公共 `segments.py` 或保留薄封装。