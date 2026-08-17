# PDF 书籍前置内容（front matter）识别与分区策略

> 状态：设计讨论沉淀（v0.1，草稿待评审）
> 适用范围：书籍类 PDF（有章节结构的出版物）解析时的前置内容跳过/分区
> 参考实现：`tmp/exam-highlight/.../domains/document/parsing/`（layout/textbook/toc_resolver）
> 现状宿主：`k2skills-core/domains/datasource/pdf_source.py` + `content/normalizer/books.py`
> 目标宿主：`aha-common-utils`（公共 PDF 处理能力下沉）
> 关联文档：`docs/pdf-parsing-foundation.md`（PDF 基础解析与版面分析管线，本设计消费其 L0-L4 输出）

---

## 1. 背景与目标

### 1.1 现状

- `k2skills-core` 的 `PdfDocumentParser`：pypdf 文本层提取 + 可选 OCR 通道 → 章节聚合（`DocumentSection`），标题启发式 `_pdf_heading_level` + `_detect_table` 复用自 `books.py`。
- **没有 front matter 处理**：封面、版权页、前言、序言、目录页与正文混排进 `sections`。
- exam-highlight 参考实现只做三件事：跳过 `cover` 页（`page_role`）、把 TOC 页抽取归档、产出 `chapter_tree`——它同样**没有真正的 front matter 跳过**。
- OCR 端口（`OcrProviderPort`/`OcrLayoutBlock`/`OcrPageResult`）已上移至 `aha-common-utils.ports`，是该包承接 PDF 公共能力的既有先例。

### 1.2 目标

1. 在 `aha-common-utils` 沉淀**书籍类 PDF front matter 识别与分区**的公共能力：
   - 跨项目复用（k2skills、exam-highlight 后续迁移、其他模板项目）；
   - 与业务方言解耦（不依赖 k2skills 的 proto/表结构/领域 DTO）；
   - 确定性可测（fail-closed/fail-open 边界可配置）。
2. 将讨论中的四层信号源、软分区、失败成本模型落到可执行设计。

### 1.3 边界（非目标）

- 不做完整版面分析（依赖注入的 OCR 布局供应商）；
- 不做 LLM 主决策（LLM 只作为低层证据的输入之一）；
- 不承诺跨语种零配置（语言敏感规则可配置）；
- 文档本阶段只含设计，不含实现代码。

---

## 2. 问题重新定义

> 你要跳过的不是"前言"，而是 **"正文起点之前的全部"**。

识别"前言/序言/致谢/版权页"是**分类问题**，词汇表有长尾且存在语义陷阱（"绪论""Introduction"常是正文第一章，误杀代价最高）。

正确姿势是**定位问题**：找到"正文从哪里开始"（第一条正文锚点），`[0, anchor_page)` 全部视为 front matter。前言只是被这一个决策顺带覆盖，无需单独识别。

- 参考实现已隐含该能力：`chapter_tree` 第一个叶子节点页码即正文起点——但它只用于建树，未用于跳过。

---

## 3. 信号源分层（L0–L3）

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
- 分歧时**宁留勿删（fail-open）**——见 §5。

---

## 4. 四类实现思路（发散对比）

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
- 防止 LLM 把"绪论"当"前言"砍掉。

### 思路 D：统计异常检测（无词汇表兜底）

- 前言/正文分布差异：第一人称密度、无编号段落比例、段落长度方差、日期模式密度、致谢/疑问句式；
- embedding 聚类发现"与正文主题向量偏离的一簇前缀页"；
- 适合无章节结构的杂集；置信度确定低于 L0–L2，只作末位裁决。

---

## 5. 失败成本模型与边界裁决策略

| 错误类型 | 后果 | 频次 | 裁决 |
|---|---|---|---|
| **误杀**（正文当前言跳：绪论/第一章误判） | 正文永久丢失、引用断裂 | 低但不可接受 | **fail-open（宁留勿删）** |
| **漏跳**（前言留在正文） | 轻微噪声，检索略降 | 常见但可容忍 | 允许 |

- 边界裁决默认 **fail-open**，与数据摄取语义一致；
- 激进剔除场景：decision 记录为 metadata
  `front_matter_decision: {boundary, confidence, signals: [...]}` 供审计；
- 该模型直接复用 WP7 的 fail-closed/fail-open 判定经验——**保护性裁剪场景 fail-open，注入/越权场景 fail-closed**，两类判定动机不同，不可混淆。

---

## 6. 公共能力模块划分（`aha-common-utils` 目标形态）

遵循该包既有分层：**ports（协议）→ 纯逻辑（无 IO 依赖）→ adapters（具体实现）→ testing（fakes）**。

```
aha_common_utils/
├── pdf/                          # 新增：公共 PDF 处理能力
│   ├── __init__.py
│   ├── types.py                  # 公共类型（不依赖业务方言）
│   │   ├── PdfZone = Literal["front_matter","body","back_matter"]
│   │   ├── PdfStructuralSignal  # outline 树 / PageLabels 跨度
│   │   ├── FrontMatterDecision   # boundary/confidence/signals
│   │   └── ZonedDocumentSection  # zone + page_span + 段落 + 资产
│   ├── structural.py             # L0：pypdf outline + PageLabels 提取（纯封装）
│   ├── boundary.py               # 边界裁决引擎（L0→L1→L2→L3 级联 + 融合 + 校验）
│   ├── heuristics.py             # L3 规则（版权页/落款页/罗马页码；语言配置化）
│   └── policy.py                 # policy 类型：strategy("auto"|"outline"|"none")
│                                 #   + zone_action("drop"|"separate"|"keep")
├── ports/ocr_provider.py         # 既有：L1 布局标签源（扩展标签映射）
└── testing/fakes/...             # 既有 + pdf fakes（outline/PageLabels 构造器）
```

**分层约束**（沿用 reusable-runtime-components.md 的既有规则）：
- `pdf/` 只依赖 stdlib + pypdf + `aha_common_utils.ports.types`；
- 不 import k2skills 任何模块；不持有 proto/表/领域 DTO；
- OCR 布局标签的 front matter 扩展映射放 `pdf/` 侧，`ports/ocr_provider.py` 的 `OcrLayoutBlock` 保持原样（label 是自由字符串，无需改动端口）。

### API 草案（形态示意，非最终签名）

```python
# L0 探测
def extract_structural_signals(path: Path) -> PdfStructuralSignal:
    """outline 树首章页码 + PageLabels 跨度；无则返回空信号。"""

# 边界裁决（主入口）
def resolve_front_matter_boundary(
    *,
    signal: PdfStructuralSignal | None,
    pages: Sequence[PageProbe],       # 页码 + 页眉状态 + 布局 label 汇总
    toc_anchor: int | None,          # 来自业务侧 TOC resolver 或第一标题页
    policy: FrontMatterPolicy,
) -> FrontMatterDecision:
    """L0 命中 lock → L1/L2 校验 → L3 兜底；默认 fail-open。"""

# 分区应用（软分区，不删内容）
def apply_zones(sections: Sequence[ZonedDocumentSection], decision: FrontMatterDecision) -> list[ZonedDocumentSection]:
    """按 boundary 打 zone；front_matter 独立 section，body 起点校验不变量。"""
```

---

## 7. 落地路径（里程碑）

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 类型与 L0 探测 | `types.py` + `structural.py`（pypdf outline/PageLabels） | 5+ 本真实 PDF outline 命中率报告；无 outline 返回空信号 |
| M2 边界裁决引擎 | `boundary.py` L0→L1→L2 级联 + 不变量校验 + fail-open | 构造测试覆盖 4 类边界场景（outline 有/无、罗马页码有/无、误杀防护） |
| M3 软分区与 policy | `apply_zones` + `policy.py`（drop/separate/keep） | zone 打标不丢内容；引用坐标不失效 |
| M4 公共化迁移 | k2skills `pdf_source.py` 迁到新 API；`books.py` 标题启发式收编 | k2skills 现有 PDF 测试全绿；`aha-common-utils` 独立测试通过 |
| M5 评测集 | 20–30 本结构差异大的书人工标注正文起点 | precision/recall 报告（重点：绪论误杀率 = 0） |

## 8. 评测方案

- 语料：有 outline / 无 outline / 罗马页码 / 无页码 / 多卷 / 扫描件混排；
- 指标：正文起点定位误差（页）、误杀率（正文当 front matter）、漏跳率；
- 必需断言：**"绪论/Introduction 作为正文第一章"场景误杀率为 0**（fail-open 的硬性验收）。

---

## 9. 与现有代码的关系

| 现有资产 | 关系 |
|---|---|
| `k2skills PDF 组件（pdf_source.py）` | M4 迁移目标；L2 用的 `_pdf_heading_level`/`_detect_table` 由 `aha-common-utils` 收编后反向复用 |
| `aha-common-utils.ports.ocr_provider` | L1 布局标签源，端口不变，标签映射扩展在 pdf/ 侧 |
| exam-highlight `parsing/`（参考） | 思路来源；其 `TocStructureResolver` 可作为 L2 的业务侧实现留在各自项目，`aha-common-utils` 只收"公共、无业务方言"部分 |
| `data-toolkit-api` 传参法 | policy 参数的命名/默认值遵循既有外部工具传参手册 |

---

## 10. 决策记录（本设计已锁定）

- **D1**：问题形态为"定位正文起点"而非"分类前言"（§2）。
- **D2**：主方案 = L0 权威信号 + 软分区（思路 A）+ fail-open 边界（§3/§4/§5）。
- **D3**：LLM 只作证据输入，不做边界主决策（§4 思路 C）。
- **D4**：公共能力下沉 `aha-common-utils.pdf`，端口解耦业务方言（§6）。
- **D5**：默认 `zone_action="separate"`（软分区），`drop` 仅审计场景显式开启（§6）。
- **待决（评审征询）**：PageLabels 罗马页码与 outline 首章页码冲突时的优先级；多卷书 `zone` 是否需 `volume` 维度。