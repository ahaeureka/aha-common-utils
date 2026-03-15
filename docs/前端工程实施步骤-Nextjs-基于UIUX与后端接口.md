# 照见一念（Glimmer）前端工程实施步骤

- 文档版本：V1.1
- 产出日期：2026-03-06
- 适用对象：没有前端开发背景、但需要推进 Next.js 落地的人
- 实施依据：
  - `UI_UX/` 原型页面
  - `docs/后端接口与数据结构设计-基于UIUX原型.md`
  - `docs/前端技术选型方案-照见一念.md`

---

## 1. 先说结论：这个前端项目应该怎么做

如果你没有前端背景，最稳妥的方式不是一上来就把所有页面和接口同时做完，而是按下面这个顺序推进：

1. **先搭工程骨架**：把 Next.js、TypeScript、Tailwind、基础目录跑起来。
2. **先把 UI 原型还原成静态页面**：不接真实接口，先把页面结构、视觉和跳转做出来。
3. **再补“会话制”状态流**：围绕 `sessionId` 串联整条用户路径。
4. **再接后端接口**：先接主链路，再接历史、洞察、每日卡。
5. **最后补异常态和上线能力**：加载、错误、风险拦截、埋点、SEO、部署。

这比“先写所有接口调用，再边做页面边调样式”更容易成功。

但如果要符合 **软件工程最佳实践、Next.js 最佳实践、SEO 最佳实践**，还需要额外遵守 4 个原则：

1. **先定义分层，再写页面**：页面、业务逻辑、接口层、埋点层必须分开。
2. **先用 Mock 数据跑通，再无缝切换真实接口**：不能把假数据直接写死在页面里。
3. **先把 SEO 基础铺好，再做视觉细节**：首页、品牌页、分享页必须从一开始就按 SEO 方式建设。
4. **先预留埋点和错误监控接口**：即使后端埋点服务未生效，前端也要先完成事件结构与调用位点。

---

## 2. 你现在要做的，不是“写网页”，而是“搭一个有状态的 Web 产品”

根据原型和后端设计，这个项目不是普通官网，而是一个 **带状态流转的心理反思工具 Web App**。

它的核心链路是：

```text
提问首页
→ 稳定入口（可选）
→ 自由倾诉（可选）
→ 问题整理确认（可选）
→ 情绪识别
→ 模式选择
→ 启发结果
→ 思考卡片
→ 深度反思
→ 总结与微实验
→ 保存 / 回看 / 恢复未完成会话 / 洞察
```

后端文档已经明确，整个流程应该围绕一个 `sessionId` 运转，因此前端工程必须按 **会话制** 来设计，而不是按“页面孤岛”设计。

---

## 3. 先理解几个你会反复遇到的前端概念

如果你不是前端出身，先记住下面 5 个词就够了：

### 3.1 `Route`（路由）
就是页面地址。
例如：
- `/` 首页
- `/session/123/emotion` 情绪识别页
- `/history` 历史记录页

### 3.2 `Component`（组件）
就是可以重复使用的 UI 模块。
例如：
- 按钮
- 情绪标签
- 卡片
- 页面头部
- 风险提示块

### 3.3 `Store`（状态仓库）
用于存放多个页面都要用的数据。
本项目里最重要的是：
- 当前 `sessionId`
- 当前问题
- 当前情绪标签
- 当前模式
- 当前生成结果

### 3.4 `API SDK`
就是把后端接口封装成前端函数。
例如：
- `createDraftSession()`
- `updateSessionContext()`
- `generateAnswer()`

### 3.5 `App Router`
是 Next.js 推荐的新路由方式。这个项目建议直接使用它，因为它更适合多页面分层和 SEO。

---

## 4. 推荐技术栈：按最容易落地的方式选

建议按下面这套来，不要一开始做太多替换：

- `Next.js`：主框架
- `TypeScript`：类型安全，减少后期返工
- `Tailwind CSS`：快速还原 `UI_UX/` 原型风格
- `TanStack Query`：处理接口请求、缓存、重试
- `Zustand`：处理轻量全局状态，例如 `sessionId`
- `Zod`：做表单和接口数据校验
- `Framer Motion`：实现微动效、淡入、卡片浮动
- `shadcn/ui`：补基础组件，不自己从零造表单、弹层、按钮

如果是 MVP，不建议一开始上：
- Redux
- 微前端
- 复杂 BFF 自定义前端框架
- 过重的 CSS 方案

---

## 4.1 必须补充的软件工程原则

这部分是对“能跑起来”和“能长期维护”之间的分界线。

### A. 页面层不直接依赖后端返回结构
不要在页面里写这种逻辑：
- 直接 `fetch`
- 直接解析后端 JSON
- 直接判断业务错误码

正确做法是分 4 层：

1. **页面层 `app/`**：只负责路由、SEO、拼装页面。
2. **业务层 `features/`**：负责流程编排、状态流转、提交动作。
3. **接口层 `lib/api/`**：负责请求、错误码转换、响应校验。
4. **数据适配层 `lib/adapters/`**：把 Mock 数据或真实接口数据统一适配成前端可用结构。

### B. 任何页面都要支持 3 种数据来源
同一个页面在工程上必须能接：

1. **本地 Mock 数据**：前端独立开发时使用
2. **联调环境真实接口**：后端逐步接入时使用
3. **生产环境正式接口**：上线后使用

### C. 任何关键能力都必须可替换
至少下面这些能力要做到“可换实现、不换页面”：

- 数据源
- 埋点上报器
- 错误监控器
- 分享元信息生成器

---

## 4.2 Next.js 最佳实践：这个项目该怎么用

建议明确采用以下规则：

### A. 使用 `App Router`
原因：
- 更适合页面分层
- 更适合按路由定义 `metadata`
- 更适合后续做服务端取数与 SEO 页面

### B. 默认优先使用 Server Component
适合：
- 落地页
- SEO 内容页
- 历史详情回显页
- 分享页

只有在以下场景再使用 Client Component：
- 输入框交互
- 本地按钮状态
- 多轮对话输入
- 动效交互
- 浏览器事件监听

### C. 页面 SEO 信息必须跟路由同层维护
建议每个关键页面都维护：
- `title`
- `description`
- `keywords`
- Open Graph
- Twitter Card
- canonical
- robots 策略

### D. 数据获取原则
- **SEO 页面**：优先服务端取数
- **强交互页面**：优先客户端取数 + 缓存
- **会话流程页面**：优先客户端请求，但支持服务端首屏恢复

---

## 4.3 SEO 最佳实践：从第一天就要预留

这个项目不是纯后台工具，它有明确的 SEO 与传播诉求，所以必须从工程阶段就纳入。

### A. 哪些页面必须按 SEO 页面建设

建议优先纳入 SEO 体系：

- 首页 `/`
- 品牌介绍页 / 落地页
- 可分享结果页
- 每日卡牌分享页
- 部分历史洞察分享页（匿名、脱敏后）

### B. 哪些页面不需要强 SEO

这类页面更偏应用内部流程：

- `/session/[id]/soothing`
- `/session/[id]/unload`
- `/session/[id]/question-refine`
- `/session/[id]/emotion`
- `/session/[id]/mode`
- `/session/[id]/cards`
- `/session/[id]/reflection`
- `/session/[id]/summary`

这些页面可以重点优化体验与状态恢复，不必把 SEO 当主目标。

### C. 必做 SEO 清单

至少包括：

1. 语义化 HTML 结构
2. 唯一 `title` 与 `description`
3. Open Graph 图片预留
4. 站点地图 `sitemap`
5. `robots.txt`
6. 结构化数据 Schema 预留
7. 合理的首屏性能
8. 避免核心文案完全依赖客户端渲染

### D. 分享页最佳实践

分享页建议单独路由化，例如：
- `/share/session/[id]`
- `/share/daily-card/[date]`

这样更方便：
- 动态生成分享 `metadata`
- 做截图卡片
- 社交媒体预览
- 搜索收录

---

## 5. 推荐路由规划：直接从原型映射到 Next.js

根据 `UI_UX/` 原型，建议把页面映射成下面这些路由：

| 原型文件 | 建议路由 | 说明 |
|---|---|---|
| `UI_UX/照见一念_Glimmer.html` | `/` | 首页 / 提问入口 |
| 新增设计页 | `/session/[id]/soothing` | 稳定入口 / 先缓一缓 |
| 新增设计页 | `/session/[id]/unload` | 自由倾诉 |
| 新增设计页 | `/session/[id]/question-refine` | 问题整理确认 |
| `UI_UX/emotion_recognition.html` | `/session/[id]/emotion` | 情绪识别 |
| `UI_UX/mode_selection.html` | `/session/[id]/mode` | 模式选择 |
| `UI_UX/insight_result.html` | `/session/[id]/result` | 启发结果 |
| `UI_UX/thought_cards.html` | `/session/[id]/cards` | 思考卡片 |
| `UI_UX/deep_reflection.html` | `/session/[id]/reflection` | 深度反思 |
| `UI_UX/summary_micro_experiment.html` | `/session/[id]/summary` | 总结与微实验 |
| `UI_UX/history.html` | `/history` | 历史记录 |
| 新增设计页 | `@sheet/(...)session/[id]/resume` | 会话恢复浮层，建议用平行路由或抽屉实现 |
| `UI_UX/pattern_analysis.html` | `/insights/patterns` | 模式洞察 |
| `UI_UX/daily_card.html` | `/daily-card` | 每日卡牌 |
| `UI_UX/risk_warning.html` | `/safety/risk` | 风险分流页 |
| `UI_UX/error.html` | `/error` | 全局错误页 |
| `UI_UX/empty_state.html` | 组件态 | 空状态，通常不是独立路由 |
| `UI_UX/loading.html` | 组件态 | 加载状态，通常不是独立路由 |

### 为什么这样切？
因为后端接口本身就是分阶段设计的，前端如果也按阶段拆页面，最容易对齐接口、埋点和错误处理。

### 5.1 新增页面的路由策略建议

新增页面建议这样处理：

1. `SoothingGate`、`UnloadPage`、`QuestionRefinePage` 使用显式路由
  - 原因：它们都可能被刷新恢复、历史回跳和埋点分析命中
2. `ResumeEntrySheet` 优先做成浮层，不建议独立整页
  - 推荐方案：使用 App Router 平行路由 `@sheet`
  - 降级方案：在 `/` 或 `/history` 页面内用 Zustand + Dialog/Drawer 控制
3. “先不决定”不建议独立页面
  - 更适合作为 `QuestionRefinePage`、`AnswerPage`、`ActionPage` 内的动作分支

---

## 6. 推荐工程目录：不要从一开始就乱放文件

建议直接采用下面这套目录：

```text
src/
├─ app/
│  ├─ (marketing)/
│  ├─ page.tsx
│  ├─ history/
│  │  └─ page.tsx
│  ├─ insights/
│  │  └─ patterns/
│  │     └─ page.tsx
│  ├─ daily-card/
│  │  └─ page.tsx
│  ├─ safety/
│  │  └─ risk/
│  │     └─ page.tsx
│  ├─ session/
│  │  └─ [id]/
│  │     ├─ soothing/
│  │     │  └─ page.tsx
│  │     ├─ unload/
│  │     │  └─ page.tsx
│  │     ├─ question-refine/
│  │     │  └─ page.tsx
│  │     ├─ emotion/
│  │     │  └─ page.tsx
│  │     ├─ mode/
│  │     │  └─ page.tsx
│  │     ├─ result/
│  │     │  └─ page.tsx
│  │     ├─ cards/
│  │     │  └─ page.tsx
│  │     ├─ reflection/
│  │     │  └─ page.tsx
│  │     └─ summary/
│  │        └─ page.tsx
│  ├─ loading.tsx
│  ├─ error.tsx
│  └─ layout.tsx
│  └─ @sheet/
│     ├─ default.tsx
│     └─ (.)session/
│        └─ [id]/
│           └─ resume/
│              └─ page.tsx
├─ components/
│  ├─ ui/
│  ├─ layout/
│  ├─ ask/
│  ├─ soothing/
│  ├─ unload/
│  ├─ resume/
│  ├─ emotion/
│  ├─ mode/
│  ├─ result/
│  ├─ cards/
│  ├─ reflection/
│  ├─ summary/
│  ├─ history/
│  └─ insights/
├─ features/
│  ├─ session/
│  ├─ soothing/
│  ├─ unload/
│  ├─ resume/
│  ├─ reflection/
│  ├─ history/
│  ├─ insights/
│  ├─ daily-card/
│  └─ safety/
├─ lib/
│  ├─ api/
│  ├─ adapters/
│  ├─ mock/
│  ├─ validators/
│  ├─ analytics/
│  ├─ monitoring/
│  ├─ seo/
│  ├─ utils/
│  └─ constants/
├─ stores/
├─ types/
└─ styles/
```

### 6.1 新增页面组件树建议

下面这部分不是“所有组件都必须先写完”，而是告诉你每个新增页面最少应该拆到什么粒度，后面才不会把页面逻辑全塞进一个 `page.tsx`。

#### A. `SoothingGate`

```text
app/session/[id]/soothing/page.tsx
└─ features/soothing/SoothingGateFeature
  ├─ components/soothing/SoothingHero
  ├─ components/soothing/BreathingHalo
  ├─ components/soothing/DurationSegmentedControl
  ├─ components/soothing/SoothingProgramPicker
  ├─ components/soothing/SoothingActionRow
  └─ components/ui/PageShell
```

#### B. `UnloadPage`

```text
app/session/[id]/unload/page.tsx
└─ features/unload/UnloadFeature
  ├─ components/unload/UnloadIntroBlock
  ├─ components/unload/FreeformInputCard
  ├─ components/unload/VoiceTranscribeButton
  ├─ components/unload/TranscribeStatusChip
  ├─ components/unload/RefineActionBar
  ├─ components/unload/RefinedQuestionPreviewCard
  └─ components/ui/PageShell
```

#### C. `QuestionRefinePage`

```text
app/session/[id]/question-refine/page.tsx
└─ features/unload/QuestionRefineFeature
  ├─ components/unload/UnloadSummaryPreview
  ├─ components/unload/PrimaryQuestionCard
  ├─ components/unload/FocusOptionList
  ├─ components/unload/RefineConfidenceHint
  ├─ components/unload/RefineDecisionBar
  └─ components/ui/PageShell
```

#### D. `ResumeEntrySheet`

```text
app/@sheet/(.)session/[id]/resume/page.tsx
└─ features/resume/ResumeEntryFeature
  ├─ components/resume/ResumeEntryHeader
  ├─ components/resume/ResumeSessionMiniCard
  ├─ components/resume/ResumeStepBadge
  ├─ components/resume/ResumeActionButtons
  └─ components/ui/SheetOrDrawer
```

### 6.2 新增页面与 feature 层职责建议

#### `features/soothing/`
- 负责稳定入口交互、时长选择、完成/跳过逻辑
- 不负责持久化渲染细节，持久化通过 repository 调用

#### `features/unload/`
- 负责自由倾诉输入、问题提炼、问题确认、先不决定分流
- 是树洞链路的主编排层

#### `features/resume/`
- 负责读取可恢复会话、决定显示哪条、触发恢复动作
- 不直接决定具体跳转页面，跳转依赖接口返回的 `resumeTo`

---

## 7. Phase 0：先准备开发环境

这是你开始写代码前必须做的事。

### 7.1 安装基础环境
你需要：
- Node.js LTS
- npm 或 pnpm
- VS Code
- Git

### 7.2 新建 Next.js 工程
建议使用：
- TypeScript
- App Router
- Tailwind
- `src/` 目录
- ESLint

### 7.3 初始化依赖
工程初始化后，补充安装：
- `@tanstack/react-query`
- `zustand`
- `zod`
- `react-hook-form`
- `framer-motion`
- `clsx`
- `tailwind-merge`
- `lucide-react`
- `msw`
- `@mswjs/data`（可选）
- `sentry` 或同类监控 SDK（后续接入）

### 7.4 先完成 4 个基础文件
优先准备：
- 全局样式
- 主题颜色变量
- 基础字体
- 页面容器布局

另外必须新增 4 类基础能力：
- 数据源切换配置
- Mock Server 启动入口
- 埋点事件定义文件
- 基础 SEO 配置文件

如果已经确认后续会引入广告商业化，建议这里直接升级为 5 类基础能力，再补一类：
- 广告位配置与广告埋点定义文件

### 7.5 本阶段完成标准
你能做到以下 3 件事，就算环境搭好了：
1. 本地项目能跑起来
2. 首页能访问
3. Tailwind 样式生效

---

## 8. Phase 1：先把视觉骨架搭出来，不接后端

这一阶段的目标只有一个：

> **把 `UI_UX/` 里的页面，用 Next.js 页面重新还原出来。**

先不要急着接接口。

但这里的“不接后端”，不是“什么数据都不准备”，而是：

> **先用可替换的 Mock 数据接口把页面跑通。**

这意味着页面从第一天开始就应该通过统一 API 层取数据，而不是在组件里手写临时对象。

### 8.0 Mock 数据最佳实践

建议采用下面这套机制：

#### A. Mock 数据放在 `lib/mock/`
不要放在页面文件里。

建议拆分：
- `lib/mock/session.mock.ts`
- `lib/mock/history.mock.ts`
- `lib/mock/insights.mock.ts`
- `lib/mock/daily-card.mock.ts`
- `lib/mock/safety.mock.ts`

#### B. Mock 返回结构必须与后端接口一致
原则：
- 字段名一致
- 错误码结构一致
- 状态值一致
- 分页结构一致

这样后端生效后，页面层几乎不用改。

#### C. Mock 启动方式要可切换
建议使用环境变量，例如：
- `NEXT_PUBLIC_API_MODE=mock`
- `NEXT_PUBLIC_API_MODE=live`

#### D. 自动替换原则
前端页面不要知道自己拿的是 Mock 还是真实数据。

正确方式是：
- 页面调用 `features/` 或 `lib/api/` 中统一方法
- 统一方法根据环境自动选择 Mock 或真实实现
- 后端接口生效后，只切环境变量或切 provider，不改页面组件

### 8.1 先抽离全站视觉规范
从 `UI_UX/` 原型看，这个产品的视觉规律很明确：

- 深色背景
- 琥珀金点缀
- 大圆角
- 毛玻璃感
- 大留白
- 中轴或卡片式布局
- 平缓微动效

所以先做下面这些共享设计资产：

#### A. 颜色 Token
例如：
- 背景主色
- 卡片底色
- 高亮金色
- 次级文字色
- 边框色
- 危险态颜色

#### B. 字体层级
至少定义：
- 页面标题
- 模块标题
- 正文
- 辅助文字
- 标签文字

#### C. 通用阴影和圆角
至少沉淀：
- 卡片圆角
- 按钮圆角
- 浮层阴影
- 高亮边框

### 8.2 先做基础组件
建议先做这些，后面所有页面都会用：

- `PageShell`
- `TopNav`
- `PrimaryButton`
- `SecondaryButton`
- `TagChip`
- `GlassCard`
- `SectionTitle`
- `EmptyState`
- `LoadingState`
- `ErrorState`
- `SheetOrDrawer`
- `StickyActionBar`
- `StatusBadge`

### 8.3 页面静态还原顺序
按下面顺序做，最稳：

1. 首页 `/`
2. 稳定入口页 `/session/[id]/soothing`
3. 自由倾诉页 `/session/[id]/unload`
4. 问题整理确认页 `/session/[id]/question-refine`
5. 情绪页 `/session/[id]/emotion`
6. 模式页 `/session/[id]/mode`
7. 结果页 `/session/[id]/result`
8. 卡片页 `/session/[id]/cards`
9. 深度反思页 `/session/[id]/reflection`
10. 总结页 `/session/[id]/summary`
11. 历史页 `/history`
12. 洞察页 `/insights/patterns`
13. 每日卡页 `/daily-card`
14. 风险页 `/safety/risk`

### 8.4 本阶段完成标准
- 每个页面都能打开
- 页面视觉基本接近原型
- 页面之间已有 Mock 数据跳转
- 没有接口也能完整走一遍流程

---

## 9. Phase 2：把后端接口先翻译成前端类型和 API

在接接口之前，先做“翻译层”。这一步能大幅减少后期混乱。

### 9.1 在 `types/` 中定义核心类型
优先定义这些类型：

- `SessionStatus`
- `AskSession`
- `TriggerAnswer`
- `ReflectionCard`
- `ReflectionState`
- `ReflectionTurn`
- `SummaryResult`
- `CognitiveBias`
- `FutureSelfMessage`
- `ActionPlan`
- `RiskResult`
- `UnloadDraft`
- `ResumeInfo`
- `ResumableSessionItem`
- `HistoryItem`
- `PatternSnapshot`
- `DailyCard`

### 9.2 在 `lib/api/` 中封装接口函数
建议一个域一个文件：

- `session.ts`
- `reflection.ts`
- `history.ts`
- `insights.ts`
- `daily-card.ts`
- `safety.ts`

优先实现这些函数：

- `createDraftSession()`
- `recordSoothing()`
- `submitUnloadDraft()`
- `confirmRefinedQuestion()`
- `updateSessionContext()`
- `generateSessionAnswer()`
- `getSessionDetail()`
- `listResumableSessions()`
- `resumeSession()`
- `selectReflectionCard()`
- `submitReflection()`
- `saveSession()`
- `adoptAction()`
- `getSessionList()`
- `getPatternInsights()`
- `getTodayDailyCard()`
- `checkSafety()`

### 9.2.1 增加 Repository / Provider 层，保证 Mock 与真实接口无缝切换

建议再增加一层：

- `lib/api/providers/mock/`
- `lib/api/providers/http/`
- `lib/api/repositories/`

推荐职责：

#### `providers/mock/`
返回本地 Mock 数据

#### `providers/http/`
调用真实后端接口

#### `repositories/`
对外暴露统一业务方法，例如：
- `sessionRepository.createDraft()`
- `sessionRepository.updateContext()`
- `sessionRepository.generateAnswer()`

页面和 `features/` 只调用 `repository`，不直接调用 `mock` 或 `http`。

### 9.3 给接口统一加 3 个能力
不要每个页面各自乱处理：

1. 统一错误处理
2. 统一超时处理
3. 统一返回数据校验

建议：
- 请求失败时统一转成标准错误对象
- 返回字段用 `zod` 校验
- 对 `422 RISK_BLOCKED` 做专门处理

同时再补 2 个能力：

4. **统一埋点钩子**
5. **统一 Mock/Live 切换**

建议统一接口调用流程如下：

```text
页面 / feature
→ repository
→ provider(mock/http)
→ zod 校验
→ 统一错误转换
→ 埋点上报
→ 返回页面可消费的数据
```

### 9.4 本阶段完成标准
- 前端项目里已经有明确类型定义
- 所有核心接口都已经有封装函数
- 页面还没接完没关系，但接口层不能散落在页面里
- 已经支持 Mock / Live 自动切换

---

## 9.5 埋点预留最佳实践：后端未生效前也要先落位

后端文档里已经给了关键事件建议，因此前端要从现在开始预留事件结构。

### A. 先定义统一事件模型
建议单独维护：

- `lib/analytics/events.ts`
- `lib/analytics/tracker.ts`
- `lib/analytics/providers/console.ts`
- `lib/analytics/providers/http.ts`

### B. 事件命名直接对齐后端
优先包括：

- `session_draft_created`
- `emotion_selected`
- `emotion_skipped`
- `mode_selected`
- `answer_generated`
- `card_selected`
- `reflection_turn_submitted`
- `summary_generated`
- `action_adopted`
- `session_saved`
- `risk_blocked`
- `session_failed`

如果产品已经在 PRD 中确认商业化包含广告，则前端应同步预留广告事件，至少包括：

- `ad_slot_viewed`
- `ad_clicked`
- `ad_closed`
- `reward_ad_started`
- `reward_ad_completed`
- `sponsored_card_opened`

### C. 埋点上报要做 Provider 切换
和接口同理：

- 开发期：输出到 `console` 或本地日志
- 联调期：可输出到 Mock Collector
- 后端生效后：切到真实埋点网关

### D. 页面只触发业务事件，不关心上报细节
例如页面只做：
- `track('mode_selected', payload)`

而不直接写：
- `fetch('/analytics', ...)`

这样后续替换后端埋点接口时，不需要改业务页面。

### E. 广告位预留要和组件结构一起设计

关联文档：

- [广告位配置与广告接入实施步骤.md](广告位配置与广告接入实施步骤.md)
- [广告位配置与广告接入研发Checklist.md](广告位配置与广告接入研发Checklist.md)
- [Mock与真实接口切换规范-埋点事件清单.md](Mock与真实接口切换规范-埋点事件清单.md)

不要等接入广告 SDK 时才临时插广告位。更稳妥的做法是，在 UI 还原阶段就预留统一广告容器，并把广告展示与埋点解耦。

建议新增：

- `components/ads/AdSlot.tsx`
- `components/ads/SponsoredCard.tsx`
- `lib/analytics/ad-events.ts`
- `lib/ads/config.ts`

建议每个广告位统一具备这些字段：

- `slotId`
- `slotType`（banner / native / rewarded / sponsored_card）
- `pagePath`
- `placement`（result_bottom / history_feed / daily_card_inline 等）
- `campaignId`
- `creativeId`
- `isSubscriber`
- `requestId`

展示埋点建议通过 `IntersectionObserver` 触发，而不是组件一渲染就直接上报。推荐规则：

- 广告位可见面积 ≥ 50%
- 持续可见 ≥ 1 秒
- 每次页面进入只记 1 次有效曝光

当前产品建议优先预留广告位的位置：

- 结果页底部原生推荐位
- 历史页列表中的低频信息流位
- 每日卡牌页的品牌合作卡位
- 总结页可选的专题合作卡位（仅在不干扰主任务时开启）

不建议预留广告位的位置：

- 首页提问输入区
- 生成中 Loading 页
- 深度反思输入中段
- 风险预警与安全分流页

---

## 10. Phase 3：实现“会话主链路”

这是 MVP 的核心。

### 10.1 先定义前端状态机
前端需要认识这些状态：

- `draft`
- `soothing`
- `unload_capturing`
- `question_refined`
- `context_ready`
- `answer_generating`
- `answer_ready`
- `reflection_in_progress`
- `summary_generating`
- `completed`
- `saved`
- `risk_blocked`
- `failed`

### 10.2 建立 `session store`
建议在 `stores/` 里放一个全局会话状态，至少保存：

- `sessionId`
- `questionText`
- `rawUnloadText`
- `refinedQuestionText`
- `focusOptions`
- `resumeInfo`
- `emotionTag`
- `insightMode`
- `selectedCardId`
- `status`

### 10.2A 新增路由守卫建议

新增页面后，建议做一个统一的路由守卫工具，例如 `features/session/guards.ts`，避免用户手输地址进入错误阶段。

建议规则：

- `status = draft` 才允许进入 `/emotion` 或 `/mode`
- `status = soothing` 允许进入 `/soothing`
- `status = unload_capturing` 允许进入 `/unload`
- `status = question_refined` 允许进入 `/question-refine`
- `status = answer_ready` 才允许进入 `/result` 与 `/cards`
- `status = reflection_in_progress` 才允许进入 `/reflection`
- `status = completed | saved` 才允许直接进入 `/summary`
- 不满足时统一回退到接口返回的 `nextStep` 或首页

### 10.3 首页实现步骤
对应原型：`UI_UX/照见一念_Glimmer.html`

#### 页面目标
让用户输入问题，并创建会话草稿。

#### 要做的事
1. 做问题输入框
2. 做示例问题 chips
3. 做“开始照见”按钮
4. 点击后先调用风险预检查（可选前置）
5. 再调用 `POST /api/v1/sessions/drafts`
6. 根据用户动作决定：
  - 默认提问：跳到 `/session/[id]/emotion`
  - 先缓一缓：跳到 `/session/[id]/soothing`
  - 我还说不清：跳到 `/session/[id]/unload`
7. 如果命中风险，跳转 `/safety/risk`

#### 页面依赖字段
- `questionText`
- `source`

#### 完成标准
- 能创建 `sessionId`
- 能携带问题进入下一页

### 10.3A 稳定入口页实现步骤
对应新增设计页

#### 页面目标
在用户高情绪张力时提供 20–60 秒缓冲，并将结果写入会话。

#### 要做的事
1. 展示默认 30 秒稳定方案
2. 支持切换时长和方案
3. 点击完成后调用 `POST /api/v1/sessions/{sessionId}/soothing`
4. 按用户动作分别跳转：
  - 继续提问 → `/session/[id]/emotion`
  - 先随便说说 → `/session/[id]/unload`
  - 稍后再来 → 返回首页

#### 接口
`POST /api/v1/sessions/{sessionId}/soothing`

#### 完成标准
- 完成与跳过都能被记录
- 页面刷新后不会丢失当前选择

### 10.3B 自由倾诉页实现步骤
对应新增设计页

#### 页面目标
收集碎片表达并生成可确认的主问题。

#### 要做的事
1. 渲染自由文本输入区与语音入口
2. 点击“帮我整理成问题”时调用 `POST /api/v1/sessions/{sessionId}/unload`
3. 成功后跳转 `/session/[id]/question-refine`
4. 失败时保留原文并支持重试

#### 接口
`POST /api/v1/sessions/{sessionId}/unload`

#### 完成标准
- 原始表达不因失败丢失
- 提炼结果可带到下一页确认

### 10.3C 问题整理确认页实现步骤
对应新增设计页

#### 页面目标
让用户确认主问题、选择侧重点，并决定继续、缓冲或延后。

#### 要做的事
1. 回显上一步原始表达摘要
2. 展示主问题卡与侧重点选项
3. 点击“就从这个问题开始”调用 `POST /api/v1/sessions/{sessionId}/refine-confirm`
4. 点击“先缓一缓”走 `nextAction = soothe`
5. 点击“先不决定”走 `nextAction = decide_later`

#### 接口
`POST /api/v1/sessions/{sessionId}/refine-confirm`

#### 完成标准
- 可继续、可缓冲、可延后三条路径都通
- 用户自定义改写后的问题也能被保存

### 10.4 情绪识别页实现步骤
对应原型：`UI_UX/emotion_recognition.html`

#### 页面目标
记录用户当前情绪标签。

#### 要做的事
1. 展示情绪选项
2. 支持单选
3. 支持“先跳过”
4. 点击继续后更新会话上下文
5. 跳转到模式页

#### 接口
`PATCH /api/v1/sessions/{sessionId}/context`

#### 页面状态
- 当前选中的情绪
- 是否提交中

#### 完成标准
- 用户选中或跳过后都能进入下一步
- 已选情绪会被保存

### 10.5 模式选择页实现步骤
对应原型：`UI_UX/mode_selection.html`

#### 页面目标
选择“照见模式”或“明断模式”。

#### 要做的事
1. 展示双卡片模式
2. 支持单选
3. 点击继续后提交模式
4. 提交成功后调用生成答案接口
5. 跳转到结果页

#### 接口
- `PATCH /api/v1/sessions/{sessionId}/context`
- `POST /api/v1/sessions/{sessionId}/generate-answer`

#### 完成标准
- 情绪 + 模式能成功写入会话
- 结果页能拿到答案和卡片数据

### 10.6 结果页实现步骤
对应原型：`UI_UX/insight_result.html`

#### 页面目标
展示一句启发答案和轻解释文案。

#### 页面依赖字段
- `question.text`
- `answer.answerText`
- `answer.hintText`
- `emotion.label`
- `insightMode.label`

#### 要做的事
1. 回显原问题
2. 展示主结果卡
3. 展示情绪/模式标签
4. 提供“换一个角度看看”按钮
5. 提供“再问一次”按钮

#### 页面跳转
- 去卡片页
- 回首页重开

#### 完成标准
- 页面刷新后能通过 `GET /sessions/{id}` 恢复

### 10.7 思考卡片页实现步骤
对应原型：`UI_UX/thought_cards.html`

#### 页面目标
展示 3 张反思卡片，并让用户选择进入深入反思。

#### 页面依赖字段
- `cards[]`

#### 要做的事
1. 渲染卡片列表
2. 标识心理维度
3. 支持反向验证标签
4. 点击卡片时调用选择接口
5. 跳转深入反思页

#### 接口
`POST /api/v1/sessions/{sessionId}/cards/{cardId}/select`

#### 完成标准
- 点哪张卡，就进入对应卡的反思页

### 10.8 深度反思页实现步骤
对应原型：`UI_UX/deep_reflection.html`

#### 页面目标
承接用户输入，完成多轮反思或单轮反思。

#### 页面依赖字段
- `selectedCard.title`
- `selectedCard.question`
- `reflection.turns[]`
- `reflection.mode`

#### 要做的事
1. 顶部展示选中的卡片标题和问题
2. 中间展示对话流
3. 底部展示输入框
4. 点击发送时调用反思提交接口
5. 根据返回决定：
   - 若继续追问：留在当前页
   - 若已完成总结：跳转总结页
6. 对提交内容做风控失败处理

#### 接口
- `POST /api/v1/sessions/{sessionId}/reflection`
- 必要时 `POST /api/v1/safety/check`

#### 完成标准
- 支持多轮消息追加
- 支持完成后自动跳转总结页

### 10.9 总结与微实验页实现步骤
对应原型：`UI_UX/summary_micro_experiment.html`

#### 页面目标
展示 AI 总结、认知偏差、未来自我和微实验行动。

#### 页面依赖字段
- `summary.summaryText`
- `summary.cognitiveBiases[]`
- `summary.futureSelf`
- `action.actionText`
- `action.actionReason`
- `action.tags[]`
- `action.ifThenPlan`

#### 要做的事
1. 左侧展示总结与偏差提醒
2. 展示未来自我模块
3. 右侧展示行动卡
4. 提供“带走行动”按钮
5. 提供“保存这次照见”按钮
6. 提供“再问一个问题”按钮

#### 接口
- `POST /api/v1/sessions/{sessionId}/save`
- `POST /api/v1/sessions/{sessionId}/actions/{actionId}/adopt`

#### 完成标准
- 保存和采纳动作都能落库
- 状态反馈明确

---

## 11. Phase 4：实现辅助页面

主链路完成后，再做这些。

### 11.1 历史记录页
对应原型：`UI_UX/history.html`

#### 接口
`GET /api/v1/sessions`

#### 要做的事
- 列表展示
- 搜索关键词
- 情绪筛选
- 模式筛选
- 分类筛选
- 分页
- 空状态
- 恢复未完成会话入口

#### 完成标准
- 能从列表回到具体会话详情

### 11.1A 恢复浮层实现步骤
对应新增设计页

#### 接口
- `GET /api/v1/sessions/resumable`
- `POST /api/v1/sessions/{sessionId}/resume`

#### 要做的事
- 在首页或历史页加载时读取可恢复会话
- 只展示优先级最高的一条，必要时提供“查看其他”
- 根据 `resumeTo` 自动跳转到 `/session/[id]/question-refine`、`/session/[id]/reflection`、`/session/[id]/result`
- 支持关闭本次提示，不反复打扰

#### 完成标准
- 不同恢复动作能落到正确页面
- 没有可恢复会话时不出现空白弹层

### 11.2 模式洞察页
对应原型：`UI_UX/pattern_analysis.html`

#### 接口
`GET /api/v1/users/{userId}/insights/patterns`

#### 要做的事
- 洞察摘要
- 主题分布
- 情绪分布
- 卡片偏好
- 决策风格

#### 完成标准
- 数据模块化渲染，不把所有内容写死在一个组件里

### 11.3 每日卡牌页
对应原型：`UI_UX/daily_card.html`

#### 接口
`GET /api/v1/daily-cards/today`

#### 要做的事
- 展示每日卡
- 支持刷新 / 换卡交互（如果产品要）
- 支持分享按钮占位

### 11.4 风险提示页
对应原型：`UI_UX/risk_warning.html`

#### 接口来源
`POST /api/v1/safety/check`

#### 要做的事
- 展示安全标题
- 展示说明文案
- 展示支持资源
- 提供返回或求助动作

---

## 12. Phase 5：加载、错误、空状态必须独立实现

这是很多新手最容易漏掉的部分。

### 12.1 加载态
参考：`UI_UX/loading.html`

需要至少覆盖：
- 提交问题后
- 生成答案时
- 提交反思后
- 拉取历史页时

### 12.2 错误态
参考：`UI_UX/error.html`

需要区分：
- 网络错误
- 会话不存在
- AI 超时
- 数据结构异常

### 12.3 空状态
参考：`UI_UX/empty_state.html`

主要用于：
- 历史记录为空
- 洞察数据不足
- 搜索无结果

### 12.4 完成标准
- 任何异步页面都不能只有“白屏”
- 任何错误都不能只有浏览器报错

---

## 13. Phase 6：补前端工程规范，不然后面一定乱

### 13.1 组件规范
要求：
- 页面组件只负责拼装
- 业务逻辑放 `features/`
- 基础 UI 放 `components/ui/`
- 接口调用放 `lib/api/`

### 13.2 命名规范
建议：
- 组件：`PascalCase`
- 方法：`camelCase`
- 常量：`UPPER_SNAKE_CASE`
- 类型：`PascalCase`

### 13.3 提交规范
建议每个提交都聚焦一个目标，例如：
- 初始化工程
- 完成首页静态页
- 接入会话创建接口
- 完成反思页多轮交互

### 13.4 环境变量管理
至少拆分：
- 本地
- 测试
- 生产

例如保存：
- API Base URL
- 埋点 Key
- 监控 Key

---

## 14. Phase 7：测试方案

如果你没有前端背景，更要早点测试。

### 14.1 最少要做的测试

#### A. 手工流程测试
至少走 5 条：
1. 正常完成整条主链路
2. 先走稳定入口再继续
3. 自由倾诉 → 问题整理确认 → 主链路
4. 跳过情绪后继续
5. 反思多轮后完成总结
6. 风险输入被拦截
7. 历史页空状态展示正确
8. 恢复浮层把用户带回正确步骤

#### B. 组件测试
至少覆盖：
- 问题输入校验
- 模式选择
- 卡片选择
- 反思提交按钮禁用逻辑

#### C. 页面测试
至少覆盖：
- 首页
- 结果页
- 反思页
- 总结页
- 问题整理确认页
- 恢复浮层

### 14.2 验收清单
上线前至少确认：
- 所有按钮有反馈
- 所有异步请求有 loading
- 所有失败场景有 fallback
- 页面刷新不会丢 `sessionId`
- 历史进入详情能恢复状态
- 风险内容不会进入普通流程

---

## 15. 建议的实际开发顺序：按 4 周推进最稳

## 第 1 周：搭框架 + 静态页

目标：
- 初始化工程
- 建立目录
- 搭视觉系统
- 完成首页、稳定页、自由倾诉页、问题整理确认页、情绪页、模式页、结果页静态版

产出：
- 前 7 个页面可演示
- 页面风格统一

## 第 2 周：接主链路接口

目标：
- 接 `drafts`
- 接 `context`
- 接 `generate-answer`
- 完成 `sessionId` 流转

产出：
- 能从首页走到结果页

## 第 3 周：完成反思与总结

目标：
- 接选卡
- 接反思提交
- 接总结数据
- 接保存和采纳动作

产出：
- 主链路闭环完成

## 第 4 周：补辅助页面与上线能力

目标：
- 历史页
- 洞察页
- 每日卡
- 风险页
- 埋点、错误、加载、部署

产出：
- MVP 可上线

---

## 16. 对没有前端背景的人，最重要的 10 条执行建议

1. **先做静态页面，再接接口。**
2. **不要在页面里直接写所有请求。**
3. **不要把所有状态都塞进全局 store。**
4. **不要一开始就追求“组件特别抽象”。**
5. **先把主链路跑通，再做历史和洞察。**
6. **先保证结构正确，再追求动画精致。**
7. **所有接口先定义类型，再开始渲染。**
8. **任何失败场景都要有页面反馈。**
9. **围绕 `sessionId` 思考，而不是围绕单页面思考。**
10. **MVP 不要试图一次做 App、小程序、Web 三端。**

---

## 17. MVP 必做清单

如果时间有限，只做下面这些就够形成第一个可上线版本：

### 必做页面
- 首页
- 情绪识别页
- 模式选择页
- 启发结果页
- 思考卡片页
- 深度反思页
- 总结与微实验页
- 风险提示页
- 历史记录页（可做简版）

### 必做接口
- `POST /api/v1/sessions/drafts`
- `PATCH /api/v1/sessions/{sessionId}/context`
- `POST /api/v1/sessions/{sessionId}/generate-answer`
- `GET /api/v1/sessions/{sessionId}`
- `POST /api/v1/sessions/{sessionId}/cards/{cardId}/select`
- `POST /api/v1/sessions/{sessionId}/reflection`
- `POST /api/v1/sessions/{sessionId}/save`
- `POST /api/v1/safety/check`

### 可后置能力
- 每日卡牌高级交互
- 模式洞察高级可视化
- 分享生成图
- 国际化
- 用户体系增强

---

## 18. 最终实施建议

如果要把这份文档压缩成一句话：

> 先用 Next.js 把 `UI_UX/` 原型还原成可点击静态流程，再围绕 `sessionId` 把后端分阶段接口接进去，最后补历史、洞察、风险和上线能力。

对于你现在的阶段，最正确的起点不是“立刻写复杂功能”，而是：

1. 先初始化 Next.js 工程
2. 先搭首页到总结页的静态版
3. 再从 `drafts` 接口开始，一步步串起来

---

## 19. 下一步建议（直接执行）

你现在最适合立刻开始的第一批任务是：

### 任务 1
初始化 Next.js 项目，并把基础目录搭出来。

### 任务 2
把下面 7 个页面先做成静态版：
- 首页
- 情绪页
- 模式页
- 结果页
- 卡片页
- 反思页
- 总结页

### 任务 3
建立 `types/session.ts` 和 `lib/api/session.ts`。

### 任务 4
先只接 3 个接口：
- 创建草稿
- 更新上下文
- 生成答案

完成这 4 步后，你的项目就真正进入“可研发状态”了。
