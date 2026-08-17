# PDF 公共处理能力：基础解析、版面分析与 front matter 分区

> 状态：设计讨论沉淀（v0.1，草稿待评审）
> 适用范围：书籍/文档类 PDF 的基础解析（文本层 + OCR 通道 + 版面分析 + 区块结构化）与前置内容（front matter）识别/分区
> 参考实现：`tmp/exam-highlight/.../domains/document/parsing/`（layout/textbook/toc_resolver）
> 现状宿主：`k2skills-core/domains/datasource/pdf_source.py` + `content/normalizer/books.py` + `text_html.py`
> 目标宿主：`aha-common-utils`（公共 PDF 能力下沉，业务端只消费结构化输出）
> 合并说明：本文件合并自 `pdf-parsing-foundation.md`（管线总纲）与 `pdf-frontmatter-strategy.md`（front matter 专项），两份原文档已删除。

---

## 1. 背景与目标

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
| **front matter 处理** | 无 | 封面、版权页、前言、序言、目录页与正文混排进 `sections` |

**核心问题**：通用能力与业务方言耦合——`pdf_source.py` 直接 import `books.py`/`text_html.py` 内部符号，任何一个业务项目要用 PDF 管线都只能整包搬 or 手写重造。

exam-highlight 参考实现只做三件事：跳过 `cover` 页（`page_role`）、把 TOC 页抽取归档、产出 `chapter_tree`——它同样**没有真正的 front matter 跳过**。

### 1.2 目标

1. 把 **PDF 基础解析 + 版面分析 + front matter 分区** 作为公共能力下沉 `aha-common-utils`：
   - 文本层提取（pypdf / 可注入提取器）；
   - OCR 通道编排（复用既有 `OcrProviderPort`）；
   - 版面分析（OCR 布局标签 → 通用块类型）；
   - 段落拆分 / 标题级启发式 / 表格检测与 CSV 渲染；
   - 页图与表格资产提取；
   - front matter 边界识别与分区（软分区，可配置 drop/separate/keep）；
   - 结构化输出契约（业务无关的 `PdfDocument` 模型）。
2. **业务端只消费输出数据**做业务映射（endpoint IR、检索单元、编译输入……），不碰解析细节。
3. 消除 `_pypdf_extract` 等重复实现。

### 1.3 边界（非目标）

- 不做业务方言：无 k2skills proto / 表 / DTO 依赖；
- 不代行业务决策：章节如何映射为 endpoint、检索单元如何切割，由业务端基于输出契约决定；
- 版面分析只做"标签→块类型 + 层级"结构化，不做像素级 OCR 引擎（引擎走注入的 OcrProviderPort）；
- 不做 LLM 主决策（LLM 只作为低层证据的输入之一），且 LLM 一律以**依赖注入**接入——复用 `aha_common_utils.llm`（provider_registry）与 `aha_common_utils.ports.llm_provider`（`LLMProviderPort`），`pdf/` 包内绝不直接构造或持有具体 provider；
- 不承诺跨语种零配置（语言敏感规则可配置）；
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
   ├─ L0c 资产提取（页图）──►    ├─ L3 资产渲染：表格 CSV / 页图字节
   │                            ├─ L4 章节聚合：heading 驱动 → 通用 Section
   │                            └─ L5 front matter 分区：边界裁决 → zone
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

## 3. 问题重定义（front matter 专项）

> 你要跳过的不是"前言"，而是 **"正文起点之前的全部"**。

识别"前言/序言/致谢/版权页"是**分类问题**，词汇表有长尾且存在语义陷阱（"绪论""Introduction"常是正文第一章，误杀代价最高）。

正确姿势是**定位问题**：找到"正文从哪里开始"（第一条正文锚点），`[0, anchor_page)` 全部视为 front matter。前言只是被这一个决策顺带覆盖，无需单独识别。

- 参考实现已隐含该能力：`chapter_tree` 第一个叶子节点页码即正文起点——但它只用于建树，未用于跳过。

---

## 4. 信号源分层（L0–L3，front matter 边界裁决）

按可靠性降序；**自上而下探测，命中即 lock，下层降级为校验**。

### L0 结构化权威信号（PDF 原生，成本≈0）

| 信号 | 来源 | 内容 | 命中即得 |
|---|---|---|---|
| PDF outline / 书签树 | `pypdf.PdfReader.outline` | 出版社数字版几乎必内嵌 | 第一个顶级书签页码 = 正文起点；顺带获得权威章节树 |
| PDF PageLabels | `pypdf` `/PageLabels` | front matter 罗马数字、正文阿拉伯 1 重新起 | 最后一个罗马页 = 前言末页；边界精确 |

> 仅对"有章节结构的书籍类 PDF"保证；扫描件/纯图片 PDF 无此层，降级到 L1/L2。

### L1 布局/版面信号（参考已用到，扩展）

- 沿用 `OcrLayoutBlock.label` 体系；**新增 front matter 专有标签**：
  `book_cover` / `copyright` / `preface` / `dedication`（映射表可配置）。
- **页眉状态变化**：正文页必有页眉（章名/书名），front matter 页通常无页眉或仅有书名页眉——页眉状态翻转即边界。
- **页码位置**：front matter 页码居中底部，正文页码外侧（奇数右/偶数左）——页码 bbox 的横向位移也是信号。

### L2 目录锚点（参考已有，改造为跳过逻辑）

- `chapter_tree` 第一个正式章节页码 `T` → `[0, T)` 为 front matter。
- 无目录树时：第一个匹配 `第X章/第X篇/Chapter N/Part N`（复用 `_CHAPTER_PREFIX` 类规则）的标题页。

### L3 启发式兜底（仅低置信度裁决）

- 版权页特征：ISBN / CIP / 出版社 / `© 2024` → 锚定版权页，其后序言页数通常有限；
- 落款页特征：人名 + 署名 + 日期（"2023 年 夏"）→ 前言结束标记；
- 罗马数字页码出现（无 PageLabels 时从页脚 OCR 文本猜）。

### 融合原则

- 多个独立信号指向同一边界才跳过（如 outline 首章页码 ≈ 页眉状态翻转点 ≈ 页码从罗马转阿拉伯）；
- 分歧时**宁留勿删（fail-open）**——见 §7。

---

## 5. 四类实现思路（front matter 分区，发散对比）

### 思路 A：软分区取代硬删除（推荐主方案）

不删，给文档单元加 `zone: "front_matter" | "body" | "back_matter"`：

- front matter 独立成"前册 section"；
- **检索侧降权而非隔离**：前言中的"本书面向读者""符号约定"有时是高价值上下文，硬删会丢；
- **引用保全**：坐标系统（`CitationCoordinateRef` 式溯源）不因跳过而失效；
- 下游以 policy 决定：`drop` / `separate` / `keep`。

### 思路 B：负向锚点 + 结构不变量校验（安全网）

不找前言，校验**结构不变量**：

- 目录页码严格递增；
- 正文首个标题页码 ≈ 目录最小页码 ± 容差；
- 推得的正文起点破坏递增性 → 声明低置信度、回退 fail-open。

> 把"判断"变成"验证"，鲁棒性完全不同。

### 思路 C：LLM 只做建议、规则做决定（与现有 fail-closed 哲学一致）

- L0/L1 全落空且处于边界模糊区的少量页面（如"序"页片段），带版面特征 + 文本给 LLM 打标；
- 最终边界由确定性规则锁死；LLM 输出只是证据加权的一项输入；
- 防止 LLM 把"绪论"当"前言"砍掉；
- **接入方式**：LLM 经 `LLMProviderPort` 依赖注入（`complete_json` 打标），`PdfPipelineConfig.llm` 注入；测试用 `FakeLLMProvider`（`aha_common_utils.testing.fakes.llm_provider`），生产用 `create_llm_provider(LLMProviderConfig)` 由调用方构造——`pdf/` 包内不依赖任何具体 provider 实现。

### 思路 D：统计异常检测（无词汇表兜底）

- 前言/正文分布差异：第一人称密度、无编号段落比例、段落长度方差、日期模式密度、致谢/疑问句式；
- embedding 聚类发现"与正文主题向量偏离的一簇前缀页"；
- 适合无章节结构的杂集；置信度确定低于 L0–L2，只作末位裁决。

---

## 6. 公共输出契约（`types.py`，业务无关）

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

# ── front matter 边界裁决专属 ──────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PdfStructuralSignal:
    """L0 权威信号：outline 树 + PageLabels 跨度。"""
    first_chapter_page: int | None = None
    page_labels: list[str] = field(default_factory=list)
    outline: JsonObject | None = None

@dataclass(frozen=True, slots=True)
class FrontMatterDecision:
    """边界裁决结果（默认 fail-open：无足够证据时 boundary=None）。"""
    boundary_page: int | None          # None = 判定为无 front matter（whole 正文）
    confidence: float
    signals: list[str]                 # 命中的信号名（audit 用）

class FrontMatterPolicy:
    strategy: str = "auto"             # auto | outline | none
    zone_action: str = "separate"      # drop | separate | keep
```

**契约规则**：只有 `Literal`/`JsonObject`/bytes，无任何领域类型——任何项目可无痛消费。

---

## 7. 失败成本模型与边界裁决策略

| 错误类型 | 后果 | 频次 | 裁决 |
|---|---|---|---|
| **误杀**（正文当前言跳：绪论/第一章误判） | 正文永久丢失、引用断裂 | 低但不可接受 | **fail-open（宁留勿删）** |
| **漏跳**（前言留在正文） | 轻微噪声，检索略降 | 常见但可容忍 | 允许 |

- 边界裁决默认 **fail-open**，与数据摄取语义一致；
- 激进剔除场景：decision 记录为 metadata
  `front_matter_decision: {boundary, confidence, signals: [...]}` 供审计；
- 该模型直接复用 WP7 的 fail-closed/fail-open 判定经验——**保护性裁剪场景 fail-open，注入/越权场景 fail-closed**，两类判定动机不同，不可混淆。

---

## 8. 管线模块划分（`aha_common_utils/pdf/`）

沿用该包既有分层 ports → 纯逻辑 → adapters → testing：

```
aha_common_utils/pdf/
├── __init__.py
├── types.py          # §6 契约
├── textlayer.py      # L0：pypdf 文本层提取（adapter：PdfTextExtractor 协议）
├── ocr_channel.py    # L0b：空页 OCR 通道编排（复用 OcrProviderPort + 页渲染注入）
├── layout.py         # L1：OcrLayoutBlock.label → PdfBlockKind 映射 + 页眉/页码规则
├── segments.py       # L2：段落拆分（收编 _split_paragraphs）+ 标题级（收编 _pdf_heading_level）
├── assets.py         # L0c/L3：页图提取 + 表格 CSV 渲染（收编 _render_table_to_csv）
├── structurer.py     # L4：heading 驱动章节聚合 → PdfSection（兼容 legacy 平铺模式）
├── structural.py     # L0：pypdf outline + PageLabels 提取（front matter 权威信号）
├── boundary.py       # L5：front matter 边界裁决引擎（L0→L1→L2→L3 级联 + 融合 + 校验）
├── heuristics.py     # L3 规则（版权页/落款页/罗马页码；语言配置化）
├── policy.py         # 解析/分区策略（strategy/zone_action/语言等）
└── pipeline.py       # 主入口：PdfPipeline.parse(path) -> PdfDocument（编排 L0→L5）
```

**分层约束**（沿用 reusable-runtime-components.md）：
- `pdf/` 只依赖 stdlib + pypdf + `aha_common_utils.ports`（ocr_provider/types）；
- 不 import 任何业务包；`PdfTextExtractor`/`OcrProviderPort`/页面渲染器均为可注入协议（测试注入 fake，生产注入真实实现）；
- `structurer.py` 的章节聚合对 k2skills 现在的 `_SectionAccumulator` 逻辑是**收编而非改写**——同样的 heading 驱动逻辑，产出公共 `PdfSection`；
- **LLM 依赖注入**：`heuristics.py`/`boundary.py` 若需 LLM 证据，仅经 `LLMProviderPort` 接口调用（复用 `aha_common_utils.ports.llm_provider` + `aha_common_utils.llm.provider_registry`），由 `PdfPipelineConfig.llm` 注入，`pdf/` 内不实例化任何具体 provider；
- OCR 布局标签的 front matter 扩展映射放 `pdf/` 侧，`ports/ocr_provider.py` 的 `OcrLayoutBlock` 保持原样（label 是自由字符串，无需改动端口）。

### 8.1 主入口 API 草案

```python
# aha_common_utils/pdf/pipeline.py（形态示意）

@dataclass(frozen=True, slots=True)
class PdfPipelineConfig:
    language: str = "Chinese"
    extract_assets: bool = True
    front_matter: str = "auto"          # auto | outline | none
    zone_action: str = "separate"       # drop | separate | keep
    page_text_extractor: PdfTextExtractor | None = None
    ocr: OcrProviderPort | None = None
    llm: LLMProviderPort | None = None      # 依赖注入（L3 启发式/思路 C 打标用；复用 ports.llm_provider）
    page_renderer: PageRenderer | None = None

class PdfPipeline:
    def __init__(self, config: PdfPipelineConfig) -> None: ...
    async def parse(self, path: str | Path) -> PdfDocument:
        """L0 文本层 → 空页 OCR → 版面块结构化 → 章节聚合 → front matter 分区。"""
        ...

# ── front matter 边界裁决（L5 内部组件）──

def extract_structural_signals(path: Path) -> PdfStructuralSignal:
    """outline 树首章页码 + PageLabels 跨度；无则返回空信号。"""

def resolve_front_matter_boundary(
    *,
    signal: PdfStructuralSignal | None,
    pages: Sequence[PageProbe],       # 页码 + 页眉状态 + 布局 label 汇总
    toc_anchor: int | None,          # 来自业务侧 TOC resolver 或第一标题页
    policy: FrontMatterPolicy,
) -> FrontMatterDecision:
    """L0 命中 lock → L1/L2 校验 → L3 兜底；默认 fail-open。"""

def apply_zones(
    sections: Sequence[PdfSection],
    decision: FrontMatterDecision,
) -> list[PdfSection]:
    """按 boundary 打 zone；front_matter 独立 section，body 起点校验不变量。"""
```

---

## 9. 收编清单（迁移时消除的重复/错位）

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
| front matter 分区 | 无 | `structural.py` + `boundary.py` + `heuristics.py`（新增） |

---

## 10. 落地路径（里程碑）

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 契约 + 文本层 | `types.py` + `textlayer.py`（收编两份 `_pypdf_extract`） | 两项目文本层行为一致；PDF 现有测试对拍 |
| M2 OCR 通道 + 版面 | `ocr_channel.py` + `layout.py` | 空页 OCR 恢复 + 布局标签映射单测 |
| M3 区块 + 资产 | `segments.py` + `assets.py` | 收编全部 k2skills 启发式；表格 CSV/页图输出不变 |
| M4 章节聚合 + 管线 | `structurer.py` + `pipeline.py` | `PdfPipeline.parse` 与 `PdfDocumentParser.parse` 输出对拍 |
| M5 front matter 权威信号 | `structural.py`（pypdf outline/PageLabels） | 5+ 本真实 PDF outline 命中率报告；无 outline 返回空信号 |
| M6 边界裁决 + 分区 | `boundary.py` + `heuristics.py` + `policy.py` | 4 类边界场景测试（outline 有/无、罗马页码有/无、误杀防护）；zone 打标不丢内容、引用坐标不失效 |
| M7 业务迁移 | k2skills `pdf_source.py`/`books.py`/`text_html.py` 改薄为消费端映射 | k2skills 全量测试绿；业务侧删重复实现 |
| M8 评测集 | 20–30 本结构差异大的书人工标注正文起点 | precision/recall 报告（重点：绪论误杀率 = 0） |

## 11. 评测与回归

- **对拍策略**：M3/M4 阶段用现有 k2skills PDF 测试作为黄金输出（sections/asset 级 diff），确保迁移零行为变化；
- **评测集语料**：有 outline / 无 outline / 罗马页码 / 无页码 / 多卷 / 扫描件混排；
- **指标**：正文起点定位误差（页）、误杀率（正文当 front matter）、漏跳率；
- **必需断言**：**"绪论/Introduction 作为正文第一章"场景误杀率为 0**（fail-open 的硬性验收）；
- 公共包独立测试 + k2skills 全量回归双轨（沿用现有 1497 基线）。

---

## 12. 与现有代码的关系

| 现有资产 | 关系 |
|---|---|
| `k2skills PDF 组件（pdf_source.py）` | M7 迁移目标；L2 用的 `_pdf_heading_level`/`_detect_table` 由 `aha-common-utils` 收编后反向复用 |
| `aha-common-utils.ports.ocr_provider` | L1 布局标签源，端口不变，标签映射扩展在 pdf/ 侧 |
| exam-highlight `parsing/`（参考） | 思路来源；其 `TocStructureResolver` 可作为 L2 的业务侧实现留在各自项目，`aha-common-utils` 只收"公共、无业务方言"部分 |
| `data-toolkit-api` 传参法 | policy 参数的命名/默认值遵循既有外部工具传参手册 |

---

## 13. 决策记录（本设计已锁定）

- **D1**：问题形态为"定位正文起点"而非"分类前言"（§3）。
- **D2**：PDF 基础解析与版面分析为公共能力，下沉 `aha-common-utils.pdf`；业务端只消费 `PdfDocument` 契约（§2/§6）。
- **D3**：输出契约业务无关（Literal/JsonObject/bytes），端口注入（extractor/ocr/渲染器）保持可测（§6/§8）。
- **D4**：既有 k2skills 启发式与章节聚合全部**收编**到公共管线，迁移期输出对拍保证零行为变化（§9/§11）。
- **D5**：front matter 主方案 = L0 权威信号 + 软分区（思路 A）+ fail-open 边界（§4/§5/§7）。
- **D6**：LLM 只作证据输入，不做边界主决策（§5 思路 C）。
- **D8**：LLM 依赖注入——仅经 `LLMProviderPort` 接口（复用 `ports/llm_provider.py` + `llm/provider_registry.py`），由 `PdfPipelineConfig.llm` 注入；`pdf/` 包内不构造/持有任何具体 provider，测试用 `FakeLLMProvider`（§5/§8）。
- **D7**：默认 `zone_action="separate"`（软分区），`drop` 仅审计场景显式开启（§6/§8）。
- **待决（评审征询）**：
  - PageLabels 罗马页码与 outline 首章页码冲突时的优先级；
  - 多卷书 `zone` 是否需 `volume` 维度；
  - `PdfAsset` 与 k2skills `SectionAsset` 的兼容迁移策略（字段直接迁移 vs 适配层）；
  - `text_html.py` 收编后其业务引用是否同步改指向公共 `segments.py` 或保留薄封装。