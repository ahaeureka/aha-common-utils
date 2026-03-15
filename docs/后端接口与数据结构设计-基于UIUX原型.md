# 照见一念（Glimmer）后端接口与数据结构设计（基于当前 UI/UX 原型）

- 产出日期：2026-03-06
- 设计依据：当前 Web 原型、PRD、开发拆解、UI/UX 设计文档
- 适用阶段：MVP / MVP+ / Beta
- 目标：基于当前页面效果图与交互流程，为后端提供一套可落地的接口、数据结构、状态流转与扩展方案

---

## 1. 结论先行

当前原型已经形成一条完整的前台体验链路：

```text
提问首页
→ 稳定入口
→ 自由倾诉整理
→ 情绪识别
→ 模式选择
→ 启发结果
→ 思考卡片
→ 深度反思
→ 总结与微实验
→ 保存 / 情绪日记 / 回访补记 / 洞察
```

从后端角度看，这条链路说明系统不能只做“单次问答返回”，而应采用 **会话制 + 分阶段生成 + 结构化结果存储** 的设计。

推荐后端采用以下原则：

1. **以 `session` 作为主聚合根**，承载一次完整照见流程。
2. **按页面阶段拆分接口**，而不是只做一个大一统接口。
3. **所有 AI 输出都必须结构化**，前端不直接依赖自然语言长文本。
4. **深度反思层兼容两种形态**：
   - MVP：单次回答
   - 扩展：多轮反思消息流
5. **历史、洞察、每日卡、风险分流** 需要独立数据域，不建议混进主会话返回里一次性塞满。

---

## 2. 当前 UI/UX 原型对后端的直接要求

### 2.1 页面与后端实体映射

| 页面 | 当前原型文件 | 后端核心实体 | 是否必须持久化 |
|---|---|---|---|
| 提问页 | UI_UX/照见一念_Glimmer.html | `session.question` | 是 |
| 稳定入口页 | 新增设计页 | `session.soothing_state`、`soothing_event` | 建议是 |
| 自由倾诉整理页 | 新增设计页 | `session.unload_draft` | 建议是 |
| 问题整理确认页 | 新增设计页 | `session.question`、`session.unload_draft.focus_options` | 建议是 |
| 情绪识别页 | UI_UX/emotion_recognition.html | `session.emotion` | 是 |
| 模式选择页 | UI_UX/mode_selection.html | `session.insightMode` | 是 |
| 启发结果页 | UI_UX/insight_result.html | `session.answer` | 是 |
| 思考卡片页 | UI_UX/thought_cards.html | `session.cards[]` | 是 |
| 深度反思页 | UI_UX/deep_reflection.html | `reflection.turns[]` / `reflection.reply` | 是 |
| 总结与微实验页 | UI_UX/summary_micro_experiment.html | `reflection.summary`、`biases[]`、`futureSelf`、`actionPlan` | 是 |
| 历史 / 情绪日记页 | UI_UX/history.html + 新增设计页 | `session_archive_view`、`journal_entry`、`followup_note` | 是 |
| 回访补记抽屉 | 新增设计页 | `followup_note`、`session_action_status` | 是 |
| 恢复入口浮层 | 新增设计页 | `resume_snapshot`、`session.status` | 建议是 |
| 模式洞察页 | UI_UX/pattern_analysis.html | `pattern_snapshot` | 是 |
| 每日卡牌页 | UI_UX/daily_card.html | `daily_card`、`daily_card_delivery` | 建议是 |
| 加载态 | UI_UX/loading.html | `generation_job` / `session.status` | 是 |
| 空状态 | UI_UX/empty_state.html | 无独立实体，依赖查询结果 | 否 |
| 错误页 | UI_UX/error.html | `error_log` / `session.error` | 是 |
| 风险提示页 | UI_UX/risk_warning.html | `risk_event`、`safety_response` | 是 |
| 用户头像/导航 | 多页面顶部导航栏 | `user_profile` | 是 |
| 设置页（前端已预留入口） | 首页导航"设置"链接 | `user_settings` | 是 |
| 底部状态栏统计 | 首页底部"已守护 N 位旅人的念头" | `global_stats` | 建议是 |

### 2.2 从效果图可反推的后端能力

#### A. 页面是“阶段式”的，不是聊天室一次输出
- 首页先录入问题。
- 情绪与模式是结果生成前的上下文补充。
- 结果页、卡片页、行动页需要分别对应不同阶段结果。

**结论：后端应支持草稿会话与阶段推进。**

#### B. `deep_reflection.html` 已经偏多轮对话
虽然文档原始定义更偏“大输入框单次回答”，但当前效果图呈现的是：
- AI 提示
- 用户回复
- AI 追问
- 再进入总结

**结论：反思层数据结构不能只保留一段 `replyText`，建议支持 `turns[]`。**

#### B2. 新增“稳定入口”和“自由倾诉整理”说明主链路前面存在缓冲层
- 用户不一定一进入就能组织成标准问题。
- 系统需要接住“先缓一缓”和“我还说不清”的状态。

**结论：后端应支持 `draft` 之前或 `draft` 早期的缓冲数据，以及从碎片表达整理为标准问题的能力。**

当前 Web 前端已按 mock-first 思路将这段缓冲层抽象为独立的 `support_draft` 聚合：

- 用户在 `UnloadPage` 阶段先生成 `supportDraftId`，此时还不强制创建正式 `sessionId`。
- 用户在 `QuestionRefinePage` 点击“就从这个问题开始”后，才通过 `support_draft` 进入主会话链路。
- “先缓一缓” 仅保留 `supportDraftId` 供前端恢复，不额外创建新写接口。
- “先不决定，先记下来” 则转换为 `followup` 上下文，进入历史补记链路。

#### C. 历史页与洞察页都需要聚合视图
这意味着不能只存最终文案，还要存：
- 问题分类
- 情绪标签
- 模式
- 选卡维度
- 偏差提示
- 行动标签
- 会话完成情况

**结论：后端需保留结构化标签字段，并支持统计。**

#### D. 导航栏含用户头像与设置入口
当前首页（`照见一念_Glimmer.html`）和历史页（`history.html`）的顶部导航栏均展示了：
- 用户圆形头像（右侧）
- "设置"导航链接（齿轮图标）

前端 `HomeFeature.tsx` 已实现头像占位 `<div className="w-8 h-8 rounded-full ..." />`。
首页底部还展示了 "已守护 1,429 位旅人的念头" 的全站统计数据。

**结论：后端需提供用户个人信息接口（头像/昵称）、用户偏好设置接口、以及全站公共统计数据接口。**

#### E. 风险页说明安全分流必须前置
风险场景不应进入普通答案链路，而应直接走安全模板。

**结论：创建会话时就要有输入风控；反思提交时还要做二次风控。**

---

## 3. 推荐的后端总体架构

推荐拆成 7 个后端域模块：

1. **User Domain**：用户注册/登录、个人信息、偏好设置
2. **Session Domain**：会话生命周期与状态机
3. **AI Orchestration Domain**：答案、卡片、总结、行动生成
4. **Safety Domain**：风险识别与分流
5. **Archive Domain**：历史记录、保存、回看
6. **Insight Domain**：问题模式与决策风格分析
7. **Content Domain**：每日卡牌、兜底文案、枚举标签、全站统计

推荐的服务划分：

```text
api-gateway
├─ user-service
├─ session-service
├─ ai-orchestrator
├─ safety-service
├─ archive-service
├─ insight-service
└─ content-service
```

MVP 也可以先做成单体应用，但内部代码结构仍建议按域拆分。

---

## 4. 会话状态机设计

### 4.1 推荐状态

```ts
type SessionStatus =
  | 'soothing'               // 正在进行稳定步骤
  | 'draft'                  // 仅录入问题
  | 'unload_capturing'       // 自由倾诉中
  | 'question_refined'       // 已整理出可用问题
  | 'context_ready'          // 已补充情绪/模式
  | 'answer_generating'      // 正在生成答案与卡片
  | 'answer_ready'           // 答案与卡片可展示
  | 'reflection_in_progress' // 已进入深度反思
  | 'summary_generating'     // 正在生成总结与微实验
  | 'completed'              // 已完成总结与行动
  | 'saved'                  // 用户主动保存
  | 'risk_blocked'           // 命中高风险，进入安全分流
  | 'failed'                 // 生成失败
  | 'archived';              // 历史归档态（可选）
```

### 4.2 状态流转

```text
soothing
→ draft
→ unload_capturing
→ question_refined
draft
→ context_ready
→ answer_generating
→ answer_ready
→ reflection_in_progress
→ summary_generating
→ completed
→ saved
```

异常流：

```text
draft/context_ready → risk_blocked
answer_generating/summary_generating → failed
```

---

## 5. 领域模型设计

## 5.1 会话聚合 `AskSession`

```ts
interface AskSession {
  sessionId: string;
  userId?: string | null;
  status: SessionStatus;

  soothingState?: SoothingState;
  unloadDraft?: UnloadDraft;

  question: {
    text: string;
    normalizedText?: string;
    category: 'career' | 'relationship' | 'life' | 'emotion' | 'self_growth' | 'other';
    source: 'manual_input' | 'example_chip' | 'history_retry';
    createdAt: string;
  };

  emotion?: {
    tag: 'anxious' | 'tired' | 'reluctant' | 'unwilling' | 'conflicted' | 'unclear' | 'lost' | 'undercurrent';
    label: string;
    source: 'user_selected' | 'model_inferred';
    confidence?: number;
    selectedAt?: string;
  };

  insightMode?: {
    code: 'reflective' | 'decisive';
    label: '照见模式' | '明断模式';
    source: 'user_selected' | 'system_recommended' | 'defaulted';
    selectedAt?: string;
  };

  answer?: TriggerAnswer;
  cards?: ReflectionCard[];
  selectedCardId?: string;
  reflection?: ReflectionState;
  summaryResult?: SummaryResult;
  actionPlan?: ActionPlan;
  resumeInfo?: ResumeInfo;
  riskResult?: RiskResult;
  saveInfo?: SaveInfo;
  metadata?: SessionMetadata;

  createdAt: string;
  updatedAt: string;
}

interface SoothingState {
  entrySource: 'home_cta' | 'answer_branch' | 'system_recommended' | 'night_mode';
  selectedDurationSeconds?: 30 | 60 | 120;
  selectedProgram?: 'breathing' | 'grounding' | 'slow_down';
  completed?: boolean;
  skipped?: boolean;
  startedAt?: string;
  finishedAt?: string;
}

interface UnloadDraft {
  source: 'free_text' | 'voice_transcript';
  rawText: string;
  rawTextLength: number;
  refinedQuestionText?: string;
  focusOptions?: string[];
  userConfirmedQuestionText?: string;
  selectedFocus?: string;
  decideLater?: boolean;
  refinementConfidence?: number;
  createdAt: string;
  refinedAt?: string;
}

interface ResumeInfo {
  resumableStep: 'unload' | 'question_refined' | 'answer_ready' | 'reflection_in_progress' | 'completed';
  questionPreview?: string;
  availableActions: Array<'continue_refine' | 'continue_reflection' | 'view_result' | 'dismiss'>;
  priorityScore?: number;
  updatedAt: string;
}
```

## 5.2 启发答案 `TriggerAnswer`

```ts
interface TriggerAnswer {
  answerId: string;
  answerText: string;
  hintText: string;
  answerType:
    | 'action_probe'
    | 'delay'
    | 'observe'
    | 'emotion_check'
    | 'value_check'
    | 'time_perspective'
    | 'risk_check';
  displayTags?: string[];
  generatedBy: {
    provider: string;
    model: string;
    templateVersion: string;
  };
  generatedAt: string;
}
```

## 5.3 反思卡片 `ReflectionCard`

```ts
interface ReflectionCard {
  cardId: string;
  cardType: string;
  title: string;
  description: string;
  question: string;
  psychologicalDimension:
    | 'emotion'
    | 'motivation'
    | 'risk'
    | 'value'
    | 'time'
    | 'relationship';
  isReverseCheck?: boolean;
  displayOrder: number;
  selected?: boolean;
}
```

## 5.4 深度反思 `ReflectionState`

为了兼容当前聊天式效果图，推荐这样设计：

```ts
interface ReflectionState {
  mode: 'single_reply' | 'guided_chat';
  selectedCardId: string;
  startedAt: string;
  replyText?: string; // 兼容 MVP 单次回答
  turns: ReflectionTurn[];
  finishedAt?: string;
}

interface ReflectionTurn {
  turnId: string;
  role: 'assistant' | 'user' | 'system';
  text: string;
  turnType?: 'prompt' | 'reply' | 'followup' | 'summary_transition';
  createdAt: string;
}
```

## 5.5 总结结果 `SummaryResult`

```ts
interface SummaryResult {
  summaryText: string;
  keyInsight?: string;
  cognitiveBiases?: CognitiveBias[];
  futureSelf?: FutureSelfMessage;
  generatedAt: string;
}

interface CognitiveBias {
  code:
    | 'catastrophizing'
    | 'loss_aversion'
    | 'sunk_cost'
    | 'present_bias'
    | 'external_validation'
    | 'confirmation_bias';
  label: string;
  message: string;
  confidence?: number;
}

interface FutureSelfMessage {
  role: string;
  message: string;
}
```

## 5.6 微实验行动 `ActionPlan`

```ts
interface ActionPlan {
  actionId: string;
  actionText: string;
  actionReason: string;
  actionType:
    | 'info_collect'
    | 'clarify'
    | 'emotion_stabilize'
    | 'small_probe'
    | 'self_reflection';
  tags: Array<
    'low_risk' |
    'reversible' |
    'clarify' |
    'info_collect' |
    'emotion_stabilize' |
    'small_probe'
  >;
  ifThenPlan?: string;
  estimatedMinutes?: number;
  reversible?: boolean;
  adopted?: boolean;
  adoptedAt?: string;
}

## 5.7 历史 / 情绪日记视图 `JournalEntryView`

```ts
interface JournalEntryView {
  sessionId: string;
  questionText: string;
  questionCategory: string;
  emotionBeforeTag?: string;
  emotionAfterTag?: string;
  insightMode?: 'reflective' | 'decisive';
  keyInsight?: string;
  journalNote?: string | null;
  followupNote?: string | null;
  actionStatus?: 'pending' | 'adopted' | 'paused' | 'done';
  resumable: boolean;
  tags: Array<{
    label: string;
    category: 'emotion' | 'dimension' | 'action' | 'status';
    color: 'amber' | 'blue' | 'green' | 'gray' | 'red';
  }>;
  createdAt: string;
  updatedAt: string;
}
```
```

## 5.8 用户个人信息 `UserProfile`

前端导航栏（首页、历史页、洞察页）均展示用户头像，首页还有"设置"入口。

```ts
interface UserProfile {
  userId: string;
  nickname: string;
  avatarUrl?: string | null;
  email?: string | null;
  phoneLastFour?: string | null;
  provider: 'email' | 'wechat' | 'phone' | 'anonymous';
  totalSessions: number;
  joinedAt: string;
  lastActiveAt: string;
}
```

## 5.9 用户偏好设置 `UserSettings`

对应首页导航栏"设置"入口，前端已预留 `<Link href="#">设置</Link>`。

```ts
interface UserSettings {
  userId: string;
  /** 界面语言 */
  language: 'zh-CN' | 'en';
  /** 默认启发模式 */
  defaultInsightMode?: 'reflective' | 'decisive' | null;
  /** 是否开启每日觉察卡推送 */
  dailyCardEnabled: boolean;
  /** 隐私级别 */
  privacyLevel: 'standard' | 'strict';
  /** 通知偏好 */
  notifications: {
    dailyCard: boolean;
    insightDigest: boolean;
    actionReminder: boolean;
  };
  /** 数据管理 */
  dataRetentionDays?: number | null;
  updatedAt: string;
}
```

## 5.10 全站统计 `GlobalStats`

首页底部状态栏展示 "已守护 1,429 位旅人的念头"，需要全站公共统计。

```ts
interface GlobalStats {
  totalUsersServed: number;
  totalSessionsCompleted: number;
  todayActiveUsers?: number;
  cachedAt: string;
}
```

## 5.11 风险结果 `RiskResult`

```ts
interface RiskResult {
  level: 'low' | 'medium' | 'high' | 'critical';
  hitPolicies: string[];
  blocked: boolean;
  safetyMessageTitle?: string;
  safetyMessageBody?: string;
  supportResources?: SafetyResource[];
  detectedAt: string;
}

interface SafetyResource {
  name: string;
  type: 'hotline' | 'hospital' | 'local_service' | 'emergency';
  value: string;
  link?: string;
}
```

---

## 6. 接口设计建议

## 6.1 方案选择

### 推荐方案：分阶段接口

原因：
- 最贴合当前原型页面流程。
- 支持用户在情绪页、模式页来回修改。
- 更容易做失败重试与埋点。
- 更适合未来扩展异步生成。

---

## 6.2 接口一：创建会话草稿

### `POST /api/v1/sessions/drafts`

### 用途
- 用户在首页输入问题后创建会话。
- 还未真正生成答案，只先创建 `draft`。

### 请求

```json
{
  "questionText": "我要不要离开现在的工作？",
  "source": "manual_input"
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "status": "draft",
  "question": {
    "text": "我要不要离开现在的工作？",
    "category": "career"
  },
  "nextStep": "emotion_gate"
}
```

### 后端逻辑
1. 输入校验
2. 文本清洗
3. 初步分类
4. 风险预筛
5. 创建会话草稿

---

## 6.2A 接口一A：记录稳定入口

### `POST /api/v1/sessions/{sessionId}/soothing`

### 用途
- 对应 `SoothingGate` 页面。
- 记录用户是否进入稳定步骤、选择了哪种节律和时长。
- 可用于个性化推荐与后续埋点对账。

### 请求

```json
{
  "entrySource": "home_cta",
  "selectedProgram": "breathing",
  "selectedDurationSeconds": 30,
  "completed": true,
  "skipped": false
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "status": "draft",
  "soothingState": {
    "entrySource": "home_cta",
    "selectedProgram": "breathing",
    "selectedDurationSeconds": 30,
    "completed": true,
    "skipped": false
  }
}
```

---

## 6.2B 接口一B：自由倾诉整理

### `POST /api/v1/support/unload/analyze`

### 用途
- 对应 `UnloadPage` 页面。
- 接收碎片化表达，并创建独立的 `supportDraft`。
- 该阶段不要求先创建正式 `sessionId`，便于前端在 mock / live 模式下平滑切换。

### 请求

```json
{
  "inputText": "我最近一直很累，也不知道是不是该离开现在的工作。"
}
```

### 请求字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `inputText` | `string` | 是 | 用户当前自由倾诉内容；前端已经把文本/语音转写统一整理为一个输入字段。 |

请求约束建议：

- `inputText` 去空格后长度建议 `3–2000` 字符。
- 若未来恢复语音通道，可通过 header 或审计字段记录来源，但当前 HTTP 契约无需暴露 `source`。

### 响应

```json
{
  "id": "support_01HV...",
  "inputText": "我最近一直很累，也不知道是不是该离开现在的工作。",
  "inputSummary": "持续疲惫，正在犹豫是否离开当前工作。",
  "refinedQuestion": "我要不要因为持续疲惫而重新评估当前工作？",
  "recommendedPath": "continue_reflection",
  "options": [
    {
      "key": "energy_vs_exit",
      "title": "我是真的想离开，还是只是太累了？",
      "description": "先区分状态耗竭与方向转向。"
    },
    {
      "key": "recover_or_evaluate",
      "title": "我现在最需要恢复状态，还是评估机会？",
      "description": "先决定此刻更需要恢复还是判断。"
    }
  ],
  "createdAt": "2026-03-11T23:41:00Z",
  "updatedAt": "2026-03-11T23:41:00Z"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `string` | `supportDraftId`，用于问题聚焦页与后续恢复链路。 |
| `inputText` | `string` | 原始倾诉文本回显。 |
| `inputSummary` | `string` | 系统先做的短摘要，便于问题聚焦页展示。 |
| `refinedQuestion` | `string` | 系统提炼出的主问题。 |
| `recommendedPath` | `continue_reflection \| stabilize_first \| defer_decision` | 建议分流。 |
| `options[].key` | `string` | 侧重点稳定 key，供前端提交。 |
| `options[].title` | `string` | 侧重点标题。 |
| `options[].description` | `string` | 侧重点解释。 |
| `createdAt` | `string` | 创建时间，ISO-8601。 |
| `updatedAt` | `string` | 更新时间，ISO-8601。 |

---

## 6.2C 接口一C：确认问题整理结果

### `GET /api/v1/support/drafts/{supportDraftId}`

### 用途
- 对应 `QuestionRefinePage` 页面。
- 在页面刷新、恢复上次、或从历史链路重新进入时拉取 `supportDraft` 明细。

### 响应

响应结构与 `POST /api/v1/support/unload/analyze` 相同。

### 说明
- 当前前端路由使用 `supportDraftId` 查询参数恢复问题聚焦页，因此需要单独提供查询接口。

---

## 6.2D 接口一D：从问题聚焦页进入正式会话

### `POST /api/v1/support/refinement/start-session`

### 用途
- 对应 `QuestionRefinePage` 页面点击“就从这个问题开始”。
- 使用 `supportDraftId + optionKey + refinedQuestion` 创建正式 `session`，并进入既有 `emotion → mode → result` 主链路。
- “先缓一缓” 继续由前端保留 `supportDraftId` 并跳转稳定入口，不新增写接口。
- “先不决定” 通过回访补记上下文接口承接，见 6.10B。

### 请求

```json
{
  "supportDraftId": "support_01HV...",
  "refinedQuestion": "我要不要因为持续疲惫而重新评估当前工作？",
  "optionKey": "energy_vs_exit"
}
```

### 请求字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `supportDraftId` | `string` | 是 | 问题聚焦页当前使用的 `supportDraft`。 |
| `refinedQuestion` | `string` | 是 | 用户最终确认后的问题文本，可等于系统提炼值，也可被用户手动改写。 |
| `optionKey` | `string` | 是 | 用户选中的侧重点 key。 |

请求约束建议：

- `refinedQuestion` 去空格后长度建议 `5–300` 字符。
- `optionKey` 必须命中该 `supportDraft.options[].key` 之一。

### 响应

```json
{
  "id": "sess_01HV...",
  "status": "draft",
  "supportDraftId": "support_01HV...",
  "refinedQuestion": "我要不要因为持续疲惫而重新评估当前工作？"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `string` | 新创建的正式会话 ID。 |
| `status` | `draft` | 主链路初始状态，后续继续补充 emotion / mode。 |
| `supportDraftId` | `string` | 当前会话来自哪个 `supportDraft`。 |
| `refinedQuestion` | `string` | 写入主会话前最终采用的问题文本。 |

### 说明
- 该接口只负责“进入正式会话”这一条分支。
- `stabilize_first` 分支由前端携带 `supportDraftId` 直接跳到稳定入口。
- `defer_decision` 分支由 `POST /api/v1/history/followups/context` 生成回访补记上下文。

---

## 6.3 接口二：更新情绪与模式上下文

### `PATCH /api/v1/sessions/{sessionId}/context`

### 用途
- 对应情绪识别页和模式选择页。
- 支持只传情绪、只传模式、或两者一起传。

### 请求

```json
{
  "emotionTag": "tired",
  "insightMode": "decisive"
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "status": "context_ready",
  "emotion": {
    "tag": "tired",
    "label": "很累",
    "source": "user_selected"
  },
  "insightMode": {
    "code": "decisive",
    "label": "明断模式"
  }
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `items[].sessionId` | `string` | 可恢复会话 ID。 |
| `items[].resumableStep` | `string` | 当前最适合恢复的步骤。 |
| `items[].questionPreview` | `string` | 用于恢复浮层展示的简短问题摘要。 |
| `items[].availableActions` | `string[]` | 当前允许用户执行的恢复动作。 |
| `items[].priorityScore` | `number` | 恢复优先级分值，前端仅用于排序参考，不用于展示。 |
| `items[].updatedAt` | `string` | 最后更新时间。 |

返回约束建议：

- `items` 最多返回 `3` 条。
- 若没有可恢复会话，返回 `{ "items": [] }`。
- `availableActions` 建议只返回前端需要显示的动作，不要暴露内部状态码映射。

---

## 6.4 接口三：生成启发答案与卡片

### `POST /api/v1/sessions/{sessionId}/generate-answer`

### 用途
- 模式选择完成后触发。
- 一次返回结果页和卡片页所需数据。

### 请求

```json
{}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "status": "answer_ready",
  "question": {
    "text": "我要不要离开现在的工作？",
    "category": "career"
  },
  "emotion": {
    "tag": "tired",
    "label": "很累"
  },
  "insightMode": {
    "code": "decisive",
    "label": "明断模式"
  },
  "answer": {
    "answerId": "ans_001",
    "answerText": "试探比冲动更适合现在的你。",
    "hintText": "你也许不需要立刻离开，而是先验证外部机会。",
    "answerType": "action_probe"
  },
  "cards": [
    {
      "cardId": "card_1",
      "cardType": "value_check",
      "title": "如果不考虑对错呢？",
      "description": "先把正确性的压力放下，看看你真正想守住什么。",
      "question": "即便最后失败了，这个过程中你最想保住的东西是什么？",
      "psychologicalDimension": "value",
      "displayOrder": 1,
      "isReverseCheck": false
    }
  ],
  "quota": {
    "tier": "free",
    "dailyQuestionQuota": 10,
    "dailyReflectionQuota": 5,
    "remainingQuestionQuota": 9,
    "remainingReflectionQuota": 5,
    "extraQuestionQuota": 0,
    "extraCardsQuota": 0,
    "remainingRewardClaimsToday": 3,
    "quotaResetAt": "2026-03-07T00:00:00Z"
  }
}
```

### 说明
这里推荐 **答案与卡片同接口返回**，原因是当前原型从结果页到卡片页是顺滑过渡，且卡片是结果的延伸，不必额外再等一次。

配额约定建议：

- `quota` 应作为正式生成类接口的标准响应块返回，便于前端同步显示剩余额度。
- `remainingQuestionQuota` 对应正式提问生成次数。
- `remainingReflectionQuota` 对应多轮反思追问次数。
- 匿名 / 免费 / 订阅三档默认口径应与 PRD、技术方案保持一致：`3/0`、`10/5`、`50/20`。

---

## 6.5 接口四：获取会话详情

### `GET /api/v1/sessions/{sessionId}`

### 用途
- 页面刷新恢复
- 历史记录进入详情
- 错误重试后回填

### 响应
返回完整 `AskSession`。

---

## 6.5A 接口四A：获取可恢复会话列表

### `GET /api/v1/sessions/resumable`

### 用途
- 对应首页恢复浮层、历史页恢复入口。
- 返回当前用户最近 1–3 条可恢复会话及推荐动作。

### 响应

```json
{
  "items": [
    {
      "sessionId": "sess_01HV...",
      "resumableStep": "question_refined",
      "questionPreview": "我要不要因为持续疲惫而重新评估当前工作？",
      "availableActions": ["continue_refine", "continue_reflection", "view_result"],
      "priorityScore": 0.93,
      "updatedAt": "2026-03-11T23:41:00Z"
    }
  ]
}
```

---

## 6.5B 接口四B：恢复指定会话

### `POST /api/v1/sessions/{sessionId}/resume`

### 用途
- 由恢复浮层触发。
- 返回推荐恢复落点与当前步骤所需最小页面数据。

### 请求

```json
{
  "action": "continue_refine"
}
```

### 请求字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `action` | `continue_refine \| continue_reflection \| view_result` | 是 | 用户在恢复浮层中选择的动作。 |

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "resumeTo": "question_refine",
  "snapshot": {
    "rawText": "我最近一直很累，也不知道是不是该离开现在的工作。",
    "refinedQuestionText": "我要不要因为持续疲惫而重新评估当前工作？",
    "focusOptions": [
      "我是真的想离开，还是只是太累了？",
      "我现在最需要恢复状态，还是评估机会？"
    ]
  }
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `sessionId` | `string` | 当前恢复的会话 ID。 |
| `resumeTo` | `question_refine \| reflection_reply \| answer_page \| action_page` | 前端应跳转或打开的目标页面。 |
| `snapshot.rawText` | `string` | 当恢复到树洞链路时，用于回显原始倾诉内容。 |
| `snapshot.refinedQuestionText` | `string` | 当前提炼结果。 |
| `snapshot.focusOptions` | `string[]` | 可恢复的侧重点选项。 |

返回约束建议：

- `snapshot` 只返回目标页面所需的最小字段，避免把完整会话重复塞给前端。
- 若目标是 `answer_page` 或 `action_page`，可只返回 `sessionId + resumeTo`，前端随后调用 `GET /sessions/{id}` 拉详情。

---

## 6.5C 前端路由映射建议（新增接口对应）

| 接口 | 典型触发页面 | 成功后的前端落点 |
|---|---|---|
| `POST /api/v1/support/unload/analyze` | `UnloadPage` | `/question-refine?supportDraftId=...` |
| `GET /api/v1/support/drafts/{supportDraftId}` | `QuestionRefinePage` / 恢复入口 | `/question-refine?supportDraftId=...` |
| `POST /api/v1/support/refinement/start-session` | `QuestionRefinePage` | `/session/[id]/emotion` |
| `POST /api/v1/history/followups/context` | `QuestionRefinePage` / `ResultPage` / `ReflectionPage` | `/history/followup?followupId=...` |
| `POST /api/v1/history/followups/{followupId}` | `FollowupNotePage` | 留在当前页并刷新状态 |
| `GET /api/v1/sessions/resumable` | 首页 / 历史页 | 恢复浮层 `ResumeEntrySheet` |
| `POST /api/v1/sessions/{sessionId}/resume` | 恢复浮层 | `/session/[id]/question-refine`、`/session/[id]/reflection`、`/session/[id]/result` |

### 说明
- 当 `action = continue_reflection` 时，`resumeTo` 可返回 `reflection_reply`。
- 当 `action = view_result` 时，`resumeTo` 返回 `answer_page` 或 `action_page`。

---

## 6.6 接口五：选择反思卡片

### `POST /api/v1/sessions/{sessionId}/cards/{cardId}/select`

### 用途
- 记录用户点击哪张卡。
- 启动深度反思阶段。

### 请求

```json
{
  "entryMode": "guided_chat"
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "status": "reflection_in_progress",
  "selectedCard": {
    "cardId": "card_2",
    "title": "恐惧背后藏着什么？",
    "question": "如果你的不安是在守护某样东西，那件东西是什么？"
  },
  "reflection": {
    "mode": "guided_chat",
    "turns": [
      {
        "turnId": "turn_1",
        "role": "assistant",
        "turnType": "prompt",
        "text": "在刚才的卡片中，你似乎特别关注了关于价值的部分。"
      }
    ]
  }
}
```

---

## 6.7 接口六：提交反思回答

### `POST /api/v1/sessions/{sessionId}/reflection`

### 用途
- MVP：提交一次回答并生成最终总结。
- 扩展：提交一轮用户消息，若需要继续追问则返回下一轮 assistant turn。

### 请求（兼容多轮）

```json
{
  "selectedCardId": "card_2",
  "replyText": "我其实更怕别人觉得我是在浪费时间。",
  "mode": "guided_chat",
  "finishReflection": true
}
```

### 响应（完成总结）

```json
{
  "sessionId": "sess_01HV...",
  "status": "completed",
  "reflection": {
    "mode": "guided_chat",
    "turns": [
      {
        "turnId": "turn_2",
        "role": "user",
        "turnType": "reply",
        "text": "我其实更怕别人觉得我是在浪费时间。"
      }
    ]
  },
  "summary": {
    "summaryText": "你当前真正承受的，不只是未知本身，而是外部评价带来的控制感缺失。",
    "cognitiveBiases": [
      {
        "code": "catastrophizing",
        "label": "灾难化倾向",
        "message": "你可能在把不确定自动推演成失败。"
      }
    ],
    "futureSelf": {
      "role": "一年后的你",
      "message": "这些挣扎不会定义你，它们会成为你理解世界的纹理。"
    }
  },
  "action": {
    "actionId": "act_001",
    "actionText": "今晚花 5 分钟列出 3 件下周完全由你掌控的小事。",
    "actionReason": "先在小范围恢复掌控感，比立即解决大问题更有效。",
    "actionType": "emotion_stabilize",
    "tags": ["low_risk", "reversible", "clarify"],
    "ifThenPlan": "如果你又开始担心最坏结果，那么先完成这张清单，再继续想长期决定。",
    "estimatedMinutes": 5,
    "reversible": true
  },
  "quota": {
    "tier": "free",
    "dailyQuestionQuota": 10,
    "dailyReflectionQuota": 5,
    "remainingQuestionQuota": 9,
    "remainingReflectionQuota": 4,
    "extraQuestionQuota": 0,
    "extraCardsQuota": 0,
    "remainingRewardClaimsToday": 3,
    "quotaResetAt": "2026-03-07T00:00:00Z"
  }
}
```

### 响应（若继续追问）

```json
{
  "sessionId": "sess_01HV...",
  "status": "reflection_in_progress",
  "reflection": {
    "mode": "guided_chat",
    "turns": [
      {
        "turnId": "turn_3",
        "role": "assistant",
        "turnType": "followup",
        "text": "如果不需要向任何人证明，你最想先尝试的一步是什么？"
      }
    ]
  },
  "quota": {
    "tier": "free",
    "dailyQuestionQuota": 10,
    "dailyReflectionQuota": 5,
    "remainingQuestionQuota": 9,
    "remainingReflectionQuota": 4,
    "extraQuestionQuota": 0,
    "extraCardsQuota": 0,
    "remainingRewardClaimsToday": 3,
    "quotaResetAt": "2026-03-07T00:00:00Z"
  }
}
```

---

## 6.8 接口七：保存会话

### `POST /api/v1/sessions/{sessionId}/save`

### 请求

```json
{
  "saveSource": "action_page"
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "saved": true,
  "savedAt": "2026-03-06T12:00:00Z"
}
```

---

## 6.9 接口八：采纳微实验

### `POST /api/v1/sessions/{sessionId}/actions/{actionId}/adopt`

### 用途
- 对应“我带走这个行动”。

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "actionId": "act_001",
  "adopted": true,
  "adoptedAt": "2026-03-06T12:05:00Z"
}
```

---

## 6.10 接口九：历史记录查询

### `GET /api/v1/sessions`

### 查询参数

```text
?userId=u_001
&keyword=工作
&emotionTag=anxious
&insightMode=reflective
&category=career
&actionStatus=pending
&hasFollowup=true
&page=1
&pageSize=20
```

### 响应

```json
{
  "items": [
    {
      "sessionId": "sess_01",
      "questionText": "我要不要离开现在的工作？",
      "questionCategory": "career",
      "emotionBeforeTag": "tired",
      "emotionAfterTag": "clearer",
      "insightMode": "reflective",
      "selectedCardDimension": "value",
      "actionType": "small_probe",
      "actionStatus": "pending",
      "status": "completed",
      "saved": true,
      "journalNote": "今天真正卡住我的，是害怕被人觉得不稳定。",
      "followupNote": null,
      "resumable": true,
      "tags": [
        { "label": "起始情绪：很累", "category": "emotion", "color": "blue" },
        { "label": "反思维度：价值", "category": "dimension", "color": "gray" },
        { "label": "行动建议：低风险实验", "category": "action", "color": "green" },
        { "label": "待继续", "category": "status", "color": "amber" }
      ],
      "createdAt": "2026-03-06T11:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "total": 24
  }
}
```

---

## 6.10A 接口九A：写入一句话日记

### `PATCH /api/v1/sessions/{sessionId}/journal-note`

### 用途
- 在总结页或历史页中保存一句话情绪日记。

### 请求

```json
{
  "journalNote": "今天我真正卡住的是害怕别人觉得我不稳定。",
  "emotionAfterTag": "clearer"
}
```

### 响应

```json
{
  "sessionId": "sess_01HV...",
  "journalNote": "今天我真正卡住的是害怕别人觉得我不稳定。",
  "emotionAfterTag": "clearer",
  "updatedAt": "2026-03-06T12:01:00Z"
}
```

---

## 6.10B 接口九B：准备与写入回访补记

### `POST /api/v1/history/followups/context`

### 用途
- 对应 `QuestionRefinePage` 的“先不决定，先记下来”、`ResultPage` 的“先不决定”、以及历史页二次进入补记。
- 根据 `supportDraftId`、`sessionId` 或 `followupId` 之一返回统一的回访补记上下文。

### 请求

```json
{
  "supportDraftId": "support_01HV..."
}
```

### 请求字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `supportDraftId` | `string` | 否 | 从问题聚焦页延后决定时传入。 |
| `sessionId` | `string` | 否 | 从结果页 / 反思页进入回访补记时传入。 |
| `followupId` | `string` | 否 | 重新打开已存在的补记时传入。 |

约束建议：

- 三者至少传一个。
- 若同时传多个，以 `followupId > sessionId > supportDraftId` 的优先级解析。

### 响应

```json
{
  "id": "followup_01HV...",
  "contextType": "support_draft",
  "sourceSessionId": null,
  "sourceQuestion": "我要不要因为持续疲惫而重新评估当前工作？",
  "emotionTags": ["疲惫", "犹豫"],
  "suggestedAction": "先记录最近一周最耗能的三个时刻，再决定是恢复还是离开。",
  "note": "",
  "status": "not_started",
  "updatedAt": "2026-03-11T23:52:00Z"
}
```

### `POST /api/v1/history/followups/{followupId}`

### 用途
- 对应 `FollowupNotePage` 保存补记。
- 当前前端使用 `POST` 做 upsert，便于 mock / live provider 统一处理。

### 请求

```json
{
  "followupId": "followup_01HV...",
  "note": "后来我约了一个同行聊聊，还没有立刻辞职。",
  "status": "tried"
}
```

### 响应

```json
{
  "id": "followup_01HV...",
  "contextType": "session",
  "sourceSessionId": "sess_01HV...",
  "sourceQuestion": "我要不要因为持续疲惫而重新评估当前工作？",
  "emotionTags": ["疲惫", "犹豫"],
  "suggestedAction": "先和一个同行聊 20 分钟，确认你真正想离开的是什么。",
  "note": "后来我约了一个同行聊聊，还没有立刻辞职。",
  "status": "tried",
  "updatedAt": "2026-03-12T09:00:00Z"
}
```

---

## 6.10C 接口九C：周度情绪回看

### `GET /api/v1/users/{userId}/journal/weekly-review`

### 用途
- 为历史 / 情绪日记页和 Beta 周度回看提供聚合摘要。

### 响应

```json
{
  "weekStart": "2026-03-02",
  "weekEnd": "2026-03-08",
  "summary": "这周你多数在疲惫和犹豫中发问，但完成反思后更常回到稍微清楚一点。",
  "topEmotions": [
    { "tag": "tired", "ratio": 0.46 },
    { "tag": "conflicted", "ratio": 0.22 }
  ],
  "topThemes": [
    { "theme": "career", "ratio": 0.53 }
  ],
  "unfinishedActions": 2
}
```

---

## 6.11 接口十：问题模式与决策风格分析

### `GET /api/v1/users/{userId}/insights/patterns`

### 响应

```json
{
  "summary": "你最近的问题多数与想离开当前状态有关。",
  "themes": [
    {
      "name": "职业转型",
      "ratio": 0.58
    },
    {
      "name": "人际边界",
      "ratio": 0.24
    }
  ],
  "emotions": [
    {
      "name": "期待感",
      "ratio": 0.42
    },
    {
      "name": "轻微焦虑",
      "ratio": 0.30
    }
  ],
  "cardPreferences": [
    {
      "dimension": "value",
      "label": "价值对冲",
      "ratio": 0.33
    }
  ],
  "decisionStyle": {
    "type": "deliberate_guide",
    "label": "慎思型引导者",
    "description": "你倾向先构建风险与收益地图，再决定是否行动。",
    "strength": "高颗粒度判断",
    "advice": "在 5% 不确定性内允许自己先迈一步。"
  },
  "sampleSize": 12,
  "generatedAt": "2026-03-06T12:00:00Z"
}
```

---

## 6.12 接口十一：每日卡牌

### `GET /api/v1/daily-cards/today`

### 响应

```json
{
  "date": "2026-03-06",
  "card": {
    "cardId": "daily_20260306",
    "name": "观察",
    "description": "不带评论的观察，是人类智力的最高形式。",
    "question": "此时此刻，你正在给自己贴上什么标签？",
    "theme": "awareness"
  }
}
```

### 可选接口
- `POST /api/v1/daily-cards/{cardId}/share`
- `POST /api/v1/daily-cards/{cardId}/save-image-task`

---

## 6.13 接口十二：安全分流

### `POST /api/v1/safety/check`

适用场景：
- 创建会话前预检查
- 反思回答前二次检查

### 请求

```json
{
  "text": "我觉得活着没有意义了",
  "scene": "session_create"
}
```

### 响应

```json
{
  "blocked": true,
  "riskLevel": "critical",
  "hitPolicies": ["self_harm", "suicidal_intent"],
  "safetyResponse": {
    "title": "我们很关切你现在的情况",
    "body": "你描述的内容提示你可能正处在需要立即支持的状态。",
    "resources": [
      {
        "name": "希望24热线",
        "type": "hotline",
        "value": "400-161-9995"
      }
    ]
  }
}
```

---

## 6.14 接口十三：获取当前用户信息

### `GET /api/v1/users/me`

### 用途
- 首页、历史页、洞察页等导航栏展示用户头像与昵称。
- 前端 `HomeFeature.tsx` 导航栏右侧已实现头像占位 `<div className="w-8 h-8 rounded-full" />`。
- `HistoryFeature.tsx` 导航栏同样展示头像。

### 响应

```json
{
  "userId": "u_001",
  "nickname": "觉察旅人",
  "avatarUrl": "https://cdn.glimmer.app/avatars/u_001.jpg",
  "email": "user@example.com",
  "provider": "email",
  "totalSessions": 12,
  "joinedAt": "2026-01-15T08:00:00Z",
  "lastActiveAt": "2026-03-06T11:30:00Z"
}
```

### 说明
- 匿名用户也应返回最小信息（`provider: 'anonymous'`, `nickname: '旅人'`）。
- `avatarUrl` 为 null 时前端显示灰色渐变占位圆。

---

## 6.14A 接口十三A：获取当前用户权益与配额

### `GET /api/v1/users/me/entitlements`

### 用途
- 返回当前用户的会员层级、广告权益与当日剩余配额。
- 给前端统一判断是否展示广告、是否允许继续提问、是否允许继续多轮对话。

### 响应

```json
{
  "userId": "u_001",
  "tier": "free",
  "isSubscriber": false,
  "adFree": false,
  "dailyQuestionQuota": 10,
  "dailyReflectionQuota": 5,
  "remainingQuestionQuota": 7,
  "remainingReflectionQuota": 3,
  "extraQuestionQuota": 1,
  "extraCardsQuota": 0,
  "remainingRewardClaimsToday": 2,
  "quotaResetAt": "2026-03-07T00:00:00Z",
  "unlockedTopics": [],
  "validUntil": null
}
```

### 说明
- 匿名用户默认返回 `tier: 'anonymous'`，基础口径建议为 `dailyQuestionQuota = 3`、`dailyReflectionQuota = 0`。
- 登录免费用户默认返回 `tier: 'free'`，基础口径建议为 `10 / 5`。
- 订阅会员默认返回 `tier: 'subscriber'`，基础口径建议为 `50 / 20`。
- 广告激励带来的额外次数应通过 `extraQuestionQuota` 或 `extraCardsQuota` 单独体现，不应覆盖基础配额字段。

---

## 6.15 接口十四：更新用户信息

### `PATCH /api/v1/users/me`

### 用途
- 设置页修改昵称、头像。

### 请求

```json
{
  "nickname": "新昵称",
  "avatarUrl": "https://cdn.glimmer.app/avatars/u_001_v2.jpg"
}
```

### 响应

返回完整 `UserProfile`。

---

## 6.16 接口十五：获取/更新用户偏好设置

### `GET /api/v1/users/me/settings`

### 用途
- 首页导航栏"设置"入口对应的设置页数据加载。
- 前端 `HomeFeature.tsx` 已有 `<Link href="#">设置</Link>` 入口。

### 响应

```json
{
  "userId": "u_001",
  "language": "zh-CN",
  "defaultInsightMode": null,
  "dailyCardEnabled": true,
  "privacyLevel": "standard",
  "notifications": {
    "dailyCard": true,
    "insightDigest": false,
    "actionReminder": true
  },
  "dataRetentionDays": null,
  "updatedAt": "2026-03-06T10:00:00Z"
}
```

### `PUT /api/v1/users/me/settings`

### 请求

```json
{
  "language": "zh-CN",
  "defaultInsightMode": "reflective",
  "dailyCardEnabled": true,
  "privacyLevel": "standard",
  "notifications": {
    "dailyCard": true,
    "insightDigest": true,
    "actionReminder": true
  }
}
```

### 响应

返回完整 `UserSettings`。

---

## 6.17 接口十六：全站公共统计

### `GET /api/v1/stats/global`

### 用途
- 首页底部状态栏展示 "已守护 1,429 位旅人的念头"。
- 无需登录即可访问，建议 CDN 缓存 5 分钟。

### 响应

```json
{
  "totalUsersServed": 1429,
  "totalSessionsCompleted": 8721,
  "todayActiveUsers": 47,
  "cachedAt": "2026-03-06T12:00:00Z"
}
```

### 说明
前端当前硬编码 `已守护 1,429 位旅人的念头`，接入后应替换为 `totalUsersServed` 动态值。

---

## 6.18 接口十七：上传头像

### `POST /api/v1/users/me/avatar`

### 用途
- 设置页上传用户头像图片。

### 请求
- Content-Type: `multipart/form-data`
- 字段：`file`（图片文件，max 2MB，允许 jpg/png/webp）

### 响应

```json
{
  "avatarUrl": "https://cdn.glimmer.app/avatars/u_001_v2.jpg",
  "updatedAt": "2026-03-06T12:05:00Z"
}
```

---

## 6.19 前后端契约总表

### 6.19.1 统一成功与失败响应约定

成功响应延续各接口当前的资源直出方式；失败响应建议统一为：

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "journalNote 不能为空",
    "details": {
      "field": "journalNote"
    },
    "requestId": "req_01J..."
  }
}
```

约定：
- `code`：稳定业务码，供前端 toast、重试分支和埋点使用。
- `message`：面向前端展示或日志排查的短句。
- `details`：字段级错误、限制值、上游超时信息等扩展信息。
- `requestId`：便于后端日志追踪。

### 6.19.2 主链路与心理按摩链路契约表

| 接口 | 请求必填字段 | 关键响应字段 | 主要错误码 |
|---|---|---|---|
| `POST /api/v1/sessions/drafts` | `questionText`, `source` | `sessionId`, `status`, `question.category`, `nextStep` | `INVALID_INPUT`, `RISK_BLOCKED`, `RATE_LIMITED` |
| `POST /api/v1/sessions/{sessionId}/soothing` | `entrySource`, `completed` 或 `skipped` | `sessionId`, `status`, `soothingState` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `POST /api/v1/sessions/{sessionId}/unload` | `source`, `rawText` | `sessionId`, `status`, `unloadDraft.refinedQuestionText`, `nextStep` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE`, `AI_TIMEOUT` |
| `POST /api/v1/sessions/{sessionId}/refine-confirm` | `confirmedQuestionText`, `nextAction` | `sessionId`, `question.text`, `unloadDraft.selectedFocus`, `nextStep` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `PATCH /api/v1/sessions/{sessionId}/context` | 至少一个：`emotionTag` / `insightMode` | `sessionId`, `status`, `emotion`, `insightMode` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `POST /api/v1/sessions/{sessionId}/generate-answer` | 无 | `sessionId`, `status`, `answer`, `cards[]`, `quota.remainingQuestionQuota` | `SESSION_NOT_FOUND`, `INVALID_SESSION_STATE`, `INVALID_AI_PAYLOAD`, `AI_TIMEOUT`, `QUOTA_EXCEEDED`, `BUDGET_EXCEEDED` |
| `POST /api/v1/sessions/{sessionId}/cards/{cardId}/select` | `entryMode` | `sessionId`, `status`, `selectedCard`, `reflection.turns[]` | `SESSION_NOT_FOUND`, `CARD_NOT_FOUND`, `INVALID_SESSION_STATE` |
| `POST /api/v1/sessions/{sessionId}/reflection` | `selectedCardId`, `replyText`, `finishReflection` | `sessionId`, `status`, `reflection.turns[]`, 可选 `summary`, `action`, `quota.remainingReflectionQuota` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE`, `RISK_BLOCKED`, `AI_TIMEOUT`, `QUOTA_EXCEEDED`, `BUDGET_EXCEEDED` |
| `POST /api/v1/sessions/{sessionId}/save` | `saveSource` | `sessionId`, `saved`, `savedAt` | `SESSION_NOT_FOUND`, `INVALID_SESSION_STATE` |
| `POST /api/v1/sessions/{sessionId}/actions/{actionId}/adopt` | 无 | `sessionId`, `actionId`, `adopted`, `adoptedAt` | `SESSION_NOT_FOUND`, `ACTION_NOT_FOUND`, `INVALID_SESSION_STATE` |

### 6.19.3 历史、日记与用户域契约表

| 接口 | 请求必填字段 | 关键响应字段 | 主要错误码 |
|---|---|---|---|
| `GET /api/v1/sessions` | 建议至少带分页：`page`, `pageSize` | `items[]`, `pagination.total` | `INVALID_INPUT`, `RATE_LIMITED` |
| `GET /api/v1/sessions/resumable` | 无 | `items[].resumableStep`, `items[].availableActions` | `UNAUTHORIZED`, `RATE_LIMITED` |
| `POST /api/v1/sessions/{sessionId}/resume` | `action` | `sessionId`, `resumeTo`, `snapshot` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `PATCH /api/v1/sessions/{sessionId}/journal-note` | `journalNote` | `sessionId`, `journalNote`, `emotionAfterTag`, `updatedAt` | `SESSION_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `POST /api/v1/history/followups/context` | `supportDraftId` / `sessionId` / `followupId` 三选一 | `id`, `contextType`, `sourceQuestion`, `suggestedAction`, `status` | `FOLLOWUP_NOT_FOUND`, `INVALID_INPUT`, `INVALID_CONTEXT_SOURCE` |
| `POST /api/v1/history/followups/{followupId}` | `followupId`, `note`, `status` | `id`, `note`, `status`, `updatedAt` | `FOLLOWUP_NOT_FOUND`, `INVALID_INPUT`, `INVALID_SESSION_STATE` |
| `GET /api/v1/users/{userId}/journal/weekly-review` | `userId` | `weekStart`, `weekEnd`, `summary`, `topEmotions[]`, `unfinishedActions` | `USER_NOT_FOUND`, `INSUFFICIENT_SAMPLE_SIZE`, `RATE_LIMITED` |
| `GET /api/v1/users/{userId}/insights/patterns` | `userId` | `summary`, `themes[]`, `emotions[]`, `decisionStyle` | `USER_NOT_FOUND`, `INSUFFICIENT_SAMPLE_SIZE`, `RATE_LIMITED` |
| `GET /api/v1/users/me` | 无 | `id`, `nickname`, `avatarUrl`, `totalSessions` | `UNAUTHORIZED`, `USER_NOT_FOUND` |
| `GET /api/v1/users/me/entitlements` | 无 | `tier`, `adFree`, `remainingQuestionQuota`, `remainingReflectionQuota`, `quotaResetAt` | `UNAUTHORIZED`, `USER_NOT_FOUND` |
| `PATCH /api/v1/users/me` | 至少一个可编辑字段 | `id`, `nickname`, `avatarUrl`, `updatedAt` | `UNAUTHORIZED`, `INVALID_INPUT` |
| `GET /api/v1/users/me/settings` | 无 | `language`, `defaultInsightMode`, `privacyLevel` | `UNAUTHORIZED`, `SETTINGS_NOT_FOUND` |
| `PATCH /api/v1/users/me/settings` | 至少一个可编辑字段 | `language`, `defaultInsightMode`, `updatedAt` | `UNAUTHORIZED`, `INVALID_INPUT` |
| `GET /api/v1/stats/global` | 无 | `totalUsersServed`, `totalSessionsCompleted`, `todayActiveUsers` | `STATS_NOT_READY`, `RATE_LIMITED` |

### 6.19.4 新增错误码建议

| 业务码 | HTTP | 适用接口 | 说明 |
|---|---|---|---|
| `CARD_NOT_FOUND` | 404 | 选卡、反思 | `cardId` 不存在或不属于该会话 |
| `ACTION_NOT_FOUND` | 404 | 采纳行动 | `actionId` 不存在或不属于该会话 |
| `USER_NOT_FOUND` | 404 | 用户域查询 | 用户不存在或不可访问 |
| `UNAUTHORIZED` | 401 | 用户域接口 | 未登录或凭证失效 |
| `SETTINGS_NOT_FOUND` | 404 | 设置接口 | 用户设置尚未初始化 |
| `INSUFFICIENT_SAMPLE_SIZE` | 409 | 周度回看、模式洞察 | 历史样本不足，前端应展示空态 |
| `QUOTA_EXCEEDED` | 429 | 生成、反思、激励权益接口 | 当前用户当日提问次数或多轮对话次数已耗尽 |
| `BUDGET_EXCEEDED` | 503 | 生成、反思接口 | 平台预算已触发熔断或临时降级 |

---

## 6.20 API 命名收敛建议

### 6.20.1 命名规则

- 路径统一使用复数资源名：`sessions`、`users`、`daily-cards`。
- 资源更新使用 `PATCH`，如 `context`、`journal-note`、`followup`。
- 触发型操作使用 `POST + 子资源动作名`，仅保留真正具有副作用或生成语义的端点，如 `drafts`、`generate-answer`、`select`、`adopt`。
- path segment 统一使用 kebab-case，不混用下划线与驼峰。
- 当前用户资源统一优先使用 `users/me`，避免同一类接口同时出现 `me` 与 `{userId}` 两种风格。

### 6.20.2 推荐收敛方案

| 当前命名 | 建议口径 | 说明 |
|---|---|---|
| `POST /api/v1/sessions/{sessionId}/generate-answer` | 保留 | 生成型接口，短期内无需改名 |
| `POST /api/v1/sessions/{sessionId}/cards/{cardId}/select` | 保留 | 用户选择行为，动作语义明确 |
| `POST /api/v1/sessions/{sessionId}/save` | 保留到 V1，后续可评估为 `PATCH /api/v1/sessions/{sessionId}` | 当前前端事件已绑定 `save`，先不破坏 |
| `GET /api/v1/users/{userId}/journal/weekly-review` | 推荐新增别名 `GET /api/v1/users/me/journal/weekly-review` | 面向当前登录用户时更统一 |
| `GET /api/v1/users/{userId}/insights/patterns` | 推荐新增别名 `GET /api/v1/users/me/insights/patterns` | 与 `users/me` 域保持一致 |

### 6.20.3 前后端联调约束

- 前端类型定义使用 camelCase 字段名，不在页面层暴露 snake_case。
- 数据库字段可继续使用 snake_case，但 repository / schema adapter 层负责转换。
- 错误码只允许后端枚举表新增，不允许页面自行拼接字符串。
- 对外接口字段一旦上线，新增字段只能向后兼容追加，禁止无版本删除或改名。

---

## 7. 数据库设计建议

## 7.1 `sessions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 会话 ID |
| `user_id` | varchar null | 用户 ID |
| `status` | varchar | 会话状态 |
| `question_text` | text | 原始问题 |
| `question_normalized_text` | text null | 清洗后文本 |
| `question_category` | varchar | 问题分类 |
| `question_source` | varchar | 来源 |
| `soothing_entry_source` | varchar null | 稳定入口来源 |
| `soothing_program` | varchar null | 稳定方式，如 breathing / grounding |
| `soothing_duration_seconds` | int null | 稳定时长 |
| `soothing_completed` | boolean | 是否完成稳定步骤 |
| `emotion_tag` | varchar null | 情绪标签 |
| `emotion_after_tag` | varchar null | 反思结束后的情绪标签 |
| `emotion_label` | varchar null | 情绪中文 |
| `emotion_source` | varchar null | 用户选/模型推断 |
| `emotion_confidence` | decimal null | 推断置信度 |
| `insight_mode` | varchar null | reflective / decisive |
| `mode_source` | varchar null | 用户选/推荐 |
| `journal_note` | text null | 一句话情绪日记 |
| `followup_note` | text null | 后续补记 |
| `followup_at` | timestamp null | 补记时间 |
| `selected_card_id` | varchar null | 选中卡 |
| `risk_level` | varchar null | 风险级别 |
| `is_saved` | boolean | 是否保存 |
| `completed_at` | timestamp null | 完成时间 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

建议索引：
- `idx_sessions_user_created`
- `idx_sessions_status`
- `idx_sessions_category`
- `idx_sessions_emotion_tag`
- `idx_sessions_insight_mode`
- `idx_sessions_followup_at`

## 7.2 `session_answers`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 答案 ID |
| `session_id` | varchar fk | 会话 ID |
| `answer_type` | varchar | 答案类型 |
| `answer_text` | text | 启发语 |
| `hint_text` | text | 解释语 |
| `display_tags` | jsonb | 展示标签 |
| `model_provider` | varchar | 模型提供方 |
| `model_name` | varchar | 模型名 |
| `template_version` | varchar | Prompt/模板版本 |
| `raw_payload` | jsonb | 原始结构 |
| `created_at` | timestamp | 创建时间 |

## 7.2A `support_drafts`

用于承接 `UnloadPage` 中的自由倾诉原文与整理结果。该表在正式 `session` 创建前即可落库，因此不再强依赖 `session_id`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `session_id` | varchar fk null | 若已进入正式主链路，则回填对应会话 ID |
| `input_text` | text | 原始倾诉内容 |
| `input_summary` | text null | 系统短摘要 |
| `refined_question` | text null | 整理后的问题 |
| `recommended_path` | varchar | continue_reflection / stabilize_first / defer_decision |
| `selected_option_key` | varchar null | 进入正式会话时选中的侧重点 key |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

## 7.3 `session_cards`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `session_id` | varchar fk | 会话 ID |
| `card_id` | varchar | 业务卡片 ID |
| `card_type` | varchar | 卡片类型 |
| `title` | varchar | 标题 |
| `description` | text | 解释 |
| `question_text` | text | 引导问题 |
| `psychological_dimension` | varchar | 心理维度 |
| `is_reverse_check` | boolean | 是否反向验证 |
| `display_order` | int | 顺序 |
| `is_selected` | boolean | 是否被选中 |
| `selected_at` | timestamp null | 选中时间 |
| `created_at` | timestamp | 创建时间 |

## 7.4 `session_reflection_turns`

这是兼容当前 `deep_reflection.html` 的关键表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | turn ID |
| `session_id` | varchar fk | 会话 ID |
| `role` | varchar | assistant/user/system |
| `turn_type` | varchar | prompt/reply/followup |
| `text` | text | 文本 |
| `sequence_no` | int | 顺序 |
| `created_at` | timestamp | 创建时间 |

## 7.5 `session_summaries`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | summary ID |
| `session_id` | varchar fk | 会话 ID |
| `summary_text` | text | 总结内容 |
| `key_insight` | text null | 核心洞察 |
| `future_self_role` | varchar null | 未来自我角色 |
| `future_self_message` | text null | 未来自我内容 |
| `created_at` | timestamp | 创建时间 |

## 7.6 `session_cognitive_biases`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `session_id` | varchar fk | 会话 ID |
| `bias_code` | varchar | 偏差编码 |
| `bias_label` | varchar | 偏差名称 |
| `message` | text | 提示文案 |
| `confidence` | decimal null | 置信度 |
| `created_at` | timestamp | 创建时间 |

## 7.7 `session_actions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | action ID |
| `session_id` | varchar fk | 会话 ID |
| `action_type` | varchar | 动作类型 |
| `action_text` | text | 微实验内容 |
| `action_reason` | text | 原因 |
| `if_then_plan` | text null | If-Then |
| `estimated_minutes` | int null | 预计时长 |
| `is_reversible` | boolean | 是否可逆 |
| `action_status` | varchar null | pending / adopted / not_started / paused |
| `is_adopted` | boolean | 是否采纳 |
| `adopted_at` | timestamp null | 采纳时间 |
| `created_at` | timestamp | 创建时间 |

## 7.8 `session_action_tags`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | bigint pk | 主键 |
| `action_id` | varchar fk | action ID |
| `tag_code` | varchar | 标签编码 |
| `created_at` | timestamp | 创建时间 |

## 7.9 `session_risk_events`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 风险事件 ID |
| `session_id` | varchar null | 可空，预检查可能尚未建会话 |
| `scene` | varchar | session_create/reflection_submit |
| `risk_level` | varchar | 风险级别 |
| `blocked` | boolean | 是否拦截 |
| `hit_policies` | jsonb | 命中策略 |
| `input_excerpt` | text | 输入摘要 |
| `response_payload` | jsonb | 安全响应 |
| `created_at` | timestamp | 创建时间 |

## 7.10 `session_event_logs`

用于埋点与审计。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | bigint pk | 主键 |
| `session_id` | varchar null | 会话 ID |
| `event_name` | varchar | 事件名 |
| `event_payload` | jsonb | 扩展字段 |
| `created_at` | timestamp | 创建时间 |

## 7.10A `user_journal_weekly_snapshots`（Beta）

用于周度情绪回看与历史聚合，不替代原始会话表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `user_id` | varchar fk | 用户 ID |
| `week_start` | date | 周开始日期 |
| `week_end` | date | 周结束日期 |
| `summary_text` | text | 周度摘要 |
| `top_emotions` | jsonb | 高频情绪占比 |
| `top_themes` | jsonb | 高频主题占比 |
| `unfinished_actions` | int | 未完成行动数 |
| `created_at` | timestamp | 创建时间 |

## 7.11 `daily_cards`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 卡片 ID |
| `card_date` | date | 日期 |
| `name` | varchar | 卡牌名 |
| `description` | text | 解释 |
| `question_text` | text | 今日问题 |
| `theme` | varchar | 主题 |
| `status` | varchar | published/draft |
| `created_at` | timestamp | 创建时间 |

## 7.12 `users`

前端导航栏头像、设置页均依赖此表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 用户 ID |
| `nickname` | varchar | 昵称（首页导航右侧展示） |
| `avatar_url` | varchar null | 头像 URL（首页/历史页导航头像） |
| `email` | varchar null | 邮箱 |
| `phone_hash` | varchar null | 手机号哈希 |
| `provider` | varchar | 登录方式 email/wechat/phone/anonymous |
| `total_sessions` | int | 累计会话数 |
| `is_active` | boolean | 是否活跃 |
| `created_at` | timestamp | 注册时间 |
| `last_active_at` | timestamp | 最后活跃 |
| `updated_at` | timestamp | 更新时间 |

建议索引：
- `idx_users_email`
- `idx_users_provider`

## 7.13 `user_settings`

对应首页"设置"入口的用户偏好持久化。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `user_id` | varchar fk | 用户 ID |
| `language` | varchar | 界面语言 zh-CN/en |
| `default_insight_mode` | varchar null | 默认启发模式 |
| `daily_card_enabled` | boolean | 每日卡推送 |
| `privacy_level` | varchar | 隐私级别 standard/strict |
| `notification_daily_card` | boolean | 每日卡通知 |
| `notification_insight_digest` | boolean | 洞察周报通知 |
| `notification_action_reminder` | boolean | 行动提醒通知 |
| `data_retention_days` | int null | 数据保留天数 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

## 7.14 `global_stats`

首页底部 "已守护 N 位旅人的念头" 展示数据（缓存表或物化视图）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 快照 ID |
| `total_users_served` | int | 累计服务用户数 |
| `total_sessions_completed` | int | 累计完成会话数 |
| `today_active_users` | int | 今日活跃用户数 |
| `computed_at` | timestamp | 统计时间 |

建议以定时任务每 5 分钟刷新，或使用 Redis 缓存。

## 7.15 `user_pattern_snapshots`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 快照 ID |
| `user_id` | varchar | 用户 ID |
| `summary_text` | text | 摘要洞察 |
| `themes_payload` | jsonb | 主题分布 |
| `emotions_payload` | jsonb | 情绪分布 |
| `card_preferences_payload` | jsonb | 卡片偏好 |
| `decision_style_type` | varchar | 风格编码 |
| `decision_style_label` | varchar | 风格名称 |
| `decision_style_description` | text | 描述 |
| `sample_size` | int | 样本数 |
| `created_at` | timestamp | 创建时间 |

## 7.15A `user_entitlements`

用于存储用户当前会员层级、广告权益与可解锁专题。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `user_id` | varchar fk | 用户 ID |
| `tier` | varchar | anonymous / free / subscriber |
| `is_subscriber` | boolean | 是否为订阅会员 |
| `ad_free` | boolean | 是否去广告 |
| `extra_question_quota` | int | 激励或活动解锁的额外提问次数 |
| `extra_cards_quota` | int | 激励或活动解锁的额外卡片次数 |
| `remaining_reward_claims_today` | int | 今日剩余可领取激励次数 |
| `unlocked_topics` | jsonb | 已解锁专题 |
| `valid_until` | timestamp null | 权益有效期 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

## 7.15B `user_quota_snapshots`

用于记录用户当日基础配额与剩余额度快照，支持提问次数和多轮对话次数分开治理。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar pk | 主键 |
| `user_id` | varchar fk | 用户 ID |
| `quota_date` | date | 配额所属日期 |
| `daily_question_quota` | int | 当日正式提问总额度 |
| `daily_reflection_quota` | int | 当日多轮对话总额度 |
| `remaining_question_quota` | int | 当日剩余正式提问额度 |
| `remaining_reflection_quota` | int | 当日剩余多轮对话额度 |
| `source_breakdown` | jsonb | 基础配额、订阅增量、激励增量拆分 |
| `quota_reset_at` | timestamp | 下次重置时间 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

默认口径建议：

- 匿名用户：`3 / 0`
- 登录免费用户：`10 / 5`
- 订阅会员：`50 / 20`

## 7.16 数据库 Migration 草案

目标：将 2026-03-06 版本 schema 平滑升级到支持“稳定入口 / 自由倾诉 / 情绪日记 / 回访补记 / 周度回看”的版本。

### Migration 1：扩展 `sessions` 与 `session_actions`

```sql
ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS soothing_entry_source varchar(32),
  ADD COLUMN IF NOT EXISTS soothing_program varchar(32),
  ADD COLUMN IF NOT EXISTS soothing_duration_seconds integer,
  ADD COLUMN IF NOT EXISTS soothing_completed boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS emotion_after_tag varchar(32),
  ADD COLUMN IF NOT EXISTS journal_note text,
  ADD COLUMN IF NOT EXISTS followup_note text,
  ADD COLUMN IF NOT EXISTS followup_at timestamptz;

ALTER TABLE session_actions
  ADD COLUMN IF NOT EXISTS action_status varchar(32);
```

### Migration 2：补充新状态与约束

```sql
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS chk_sessions_status;

ALTER TABLE sessions
  ADD CONSTRAINT chk_sessions_status CHECK (
    status IN (
      'draft',
      'soothing',
      'unload_capturing',
      'question_refined',
      'context_ready',
      'answer_generating',
      'answer_ready',
      'reflection_in_progress',
      'summary_generating',
      'completed',
      'saved',
      'risk_blocked',
      'failed',
      'archived'
    )
  );
```

### Migration 3：新增承接表与聚合表

```sql
CREATE TABLE IF NOT EXISTS session_unload_drafts (...);
CREATE TABLE IF NOT EXISTS user_journal_weekly_snapshots (...);
```

### Migration 4：历史数据回填建议

- 旧数据 `session_actions.is_adopted = true` 的记录，回填 `action_status = 'adopted'`。
- 旧会话默认 `soothing_completed = false`，无需强制补历史来源。
- 已保存但无日记数据的历史记录保持空值，不做伪造回填。

### Migration 5：索引与发布顺序

建议顺序：
1. 先发数据库 migration，新增字段全部保持 nullable 或带默认值。
2. 再发后端，开始写新字段和新表。
3. 最后发前端，逐步启用稳定入口、自由倾诉、日记与补记交互。
4. 新增索引 `idx_sessions_followup_at`、`idx_session_actions_action_status` 应在低峰期执行。

### 基于当前仓库的版本化迁移建议

由于仓库当前已存在 `0009_psychological_flow_extensions.py`，新增的树洞确认与恢复能力建议继续拆成以下版本：

#### `0010_refine_confirmation_fields.py`

```sql
ALTER TABLE session_unload_drafts
  ADD COLUMN IF NOT EXISTS focus_options jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS user_confirmed_question_text text,
  ADD COLUMN IF NOT EXISTS selected_focus text,
  ADD COLUMN IF NOT EXISTS decide_later boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS refined_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_session_unload_drafts_decide_later
  ON session_unload_drafts (decide_later);
```

#### `0011_create_session_resume_snapshots.py`

```sql
CREATE TABLE IF NOT EXISTS session_resume_snapshots (
  id varchar(64) PRIMARY KEY,
  session_id varchar(64) NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
  resumable_step varchar(32) NOT NULL,
  question_preview text,
  last_emotion_tag varchar(32),
  available_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
  priority_score numeric(6,4) NOT NULL DEFAULT 0,
  resume_count integer NOT NULL DEFAULT 0,
  dismissed_at timestamptz,
  expires_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
```

#### `0012_resume_snapshot_backfill.py`

```sql
INSERT INTO session_resume_snapshots (
  id,
  session_id,
  resumable_step,
  question_preview,
  available_actions,
  priority_score,
  created_at,
  updated_at
)
SELECT
  'resume_' || id,
  id,
  CASE
  WHEN status = 'question_refined' THEN 'question_refined'
  WHEN status = 'answer_ready' THEN 'answer_ready'
  WHEN status = 'reflection_in_progress' THEN 'reflection_in_progress'
  WHEN status = 'completed' AND followup_note IS NULL THEN 'completed'
  END,
  left(question_text, 120),
  CASE
  WHEN status = 'question_refined' THEN '["continue_refine","view_result"]'::jsonb
  WHEN status = 'answer_ready' THEN '["view_result","continue_reflection"]'::jsonb
  WHEN status = 'reflection_in_progress' THEN '["continue_reflection","view_result"]'::jsonb
  ELSE '["view_result"]'::jsonb
  END,
  0.8,
  now(),
  now()
FROM sessions
WHERE status IN ('question_refined', 'answer_ready', 'reflection_in_progress', 'completed');
```

### Alembic upgrade / downgrade 设计要求

1. upgrade 中所有新列先允许空或带默认值，避免锁表回填过久。
2. downgrade 不做数据保留承诺，但必须先删索引、删约束，再删列/删表。
3. `0012` 作为数据迁移，允许 downgrade 仅删除由该版本创建的快照记录。

---

## 7.17 接口 Schema 草案（Pydantic v2）

目标：让后端可直接在 `api/schemas/session/` 下建立请求响应模型，并与当前接口契约对齐。

### 目录建议

```text
api/schemas/session/
├─ common.py
├─ unload.py
├─ resume.py
├─ context.py
├─ answer.py
└─ detail.py
```

对于用户权益与配额，建议同时补齐独立 schema：

```text
api/schemas/user/
├─ common.py
├─ profile.py
├─ settings.py
└─ entitlements.py
```

### `api/schemas/session/common.py`

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionSchemaBase(BaseModel):
  model_config = ConfigDict(extra="forbid", populate_by_name=True)


class QuestionPayload(SessionSchemaBase):
  text: str = Field(min_length=1, max_length=300)
  category: Literal["career", "relationship", "life", "emotion", "self_growth", "other"]


class ResumeInfoPayload(SessionSchemaBase):
  resumableStep: Literal[
    "unload",
    "question_refined",
    "answer_ready",
    "reflection_in_progress",
    "completed",
  ]
  questionPreview: str | None = Field(default=None, max_length=120)
  availableActions: list[Literal["continue_refine", "continue_reflection", "view_result", "dismiss"]]
  priorityScore: Decimal | None = Field(default=None, ge=0, le=1)
  updatedAt: datetime
```

### `api/schemas/session/unload.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import QuestionPayload, SessionSchemaBase


class UnloadRequest(SessionSchemaBase):
  source: Literal["free_text", "voice_transcript"]
  rawText: str = Field(min_length=3, max_length=2000)


class UnloadDraftPayload(SessionSchemaBase):
  source: Literal["free_text", "voice_transcript"]
  rawText: str
  rawTextLength: int = Field(ge=0)
  refinedQuestionText: str | None = None
  focusOptions: list[str] = Field(default_factory=list, max_length=2)
  userConfirmedQuestionText: str | None = None
  selectedFocus: str | None = None
  decideLater: bool = False
  refinementConfidence: float | None = Field(default=None, ge=0, le=1)
  createdAt: datetime | None = None
  refinedAt: datetime | None = None


class UnloadResponse(SessionSchemaBase):
  sessionId: str
  status: Literal["question_refined"]
  unloadDraft: UnloadDraftPayload
  nextStep: Literal["question_refine"]


class ConfirmRefineRequest(SessionSchemaBase):
  confirmedQuestionText: str = Field(min_length=5, max_length=300)
  selectedFocus: str | None = Field(default=None, max_length=120)
  nextAction: Literal["continue", "soothe", "decide_later"]


class ConfirmRefineResponse(SessionSchemaBase):
  sessionId: str
  status: Literal["draft", "question_refined"]
  question: QuestionPayload
  unloadDraft: UnloadDraftPayload
  nextStep: Literal["emotion_gate", "soothing_gate", "history"]
```

### `api/schemas/session/resume.py`

```python
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import ResumeInfoPayload, SessionSchemaBase


class ResumableSessionItem(SessionSchemaBase):
  sessionId: str
  resumableStep: Literal[
    "question_refined",
    "answer_ready",
    "reflection_in_progress",
    "completed",
  ]
  questionPreview: str | None = Field(default=None, max_length=120)
  availableActions: list[Literal["continue_refine", "continue_reflection", "view_result"]]
  priorityScore: float = Field(ge=0, le=1)
  updatedAt: datetime


class ResumableSessionsResponse(SessionSchemaBase):
  items: list[ResumableSessionItem] = Field(default_factory=list, max_length=3)


class ResumeSessionRequest(SessionSchemaBase):
  action: Literal["continue_refine", "continue_reflection", "view_result"]


class ResumeSnapshotPayload(SessionSchemaBase):
  rawText: str | None = None
  refinedQuestionText: str | None = None
  focusOptions: list[str] = Field(default_factory=list)


class ResumeSessionResponse(SessionSchemaBase):
  sessionId: str
  resumeTo: Literal["question_refine", "reflection_reply", "answer_page", "action_page"]
  snapshot: ResumeSnapshotPayload | None = None
```

### `api/schemas/session/detail.py`

```python
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import QuestionPayload, ResumeInfoPayload, SessionSchemaBase
from .unload import UnloadDraftPayload


class SessionDetailResponse(SessionSchemaBase):
  sessionId: str
  status: Literal[
    "draft",
    "soothing",
    "unload_capturing",
    "question_refined",
    "context_ready",
    "answer_ready",
    "reflection_in_progress",
    "completed",
    "saved",
    "risk_blocked",
    "failed",
  ]
  question: QuestionPayload
  unloadDraft: UnloadDraftPayload | None = None
  resumeInfo: ResumeInfoPayload | None = None
```

### Router 绑定建议

| 路由 | 请求 Schema | 响应 Schema |
|---|---|---|
| `POST /api/v1/sessions/{sessionId}/unload` | `UnloadRequest` | `UnloadResponse` |
| `POST /api/v1/sessions/{sessionId}/refine-confirm` | `ConfirmRefineRequest` | `ConfirmRefineResponse` |
| `GET /api/v1/sessions/resumable` | 无 | `ResumableSessionsResponse` |
| `POST /api/v1/sessions/{sessionId}/resume` | `ResumeSessionRequest` | `ResumeSessionResponse` |
| `GET /api/v1/sessions/{sessionId}` | 无 | `SessionDetailResponse` |

### `api/schemas/user/entitlements.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from api.schemas.session.common import SessionSchemaBase


class UserEntitlementsResponse(SessionSchemaBase):
  userId: str | None = None
  tier: Literal["anonymous", "free", "subscriber"]
  isSubscriber: bool
  adFree: bool
  dailyQuestionQuota: int = Field(ge=0)
  dailyReflectionQuota: int = Field(ge=0)
  remainingQuestionQuota: int = Field(ge=0)
  remainingReflectionQuota: int = Field(ge=0)
  extraQuestionQuota: int = Field(ge=0)
  extraCardsQuota: int = Field(ge=0)
  remainingRewardClaimsToday: int = Field(ge=0)
  quotaResetAt: datetime
  unlockedTopics: list[str] = Field(default_factory=list)
  validUntil: datetime | None = None


class QuotaPayload(SessionSchemaBase):
  tier: Literal["anonymous", "free", "subscriber"]
  dailyQuestionQuota: int = Field(ge=0)
  dailyReflectionQuota: int = Field(ge=0)
  remainingQuestionQuota: int = Field(ge=0)
  remainingReflectionQuota: int = Field(ge=0)
  extraQuestionQuota: int = Field(ge=0)
  extraCardsQuota: int = Field(ge=0)
  remainingRewardClaimsToday: int = Field(ge=0)
  quotaResetAt: datetime
```

建议在以下响应 Schema 中复用 `QuotaPayload`：

- `GenerateAnswerResponse`
- `ReflectionTurnResponse`
- `GetUserEntitlementsResponse`

### Schema 测试最小清单

1. `UnloadRequest.rawText` 过短时校验失败。
2. `ConfirmRefineRequest.nextAction` 不在枚举内时校验失败。
3. `ResumableSessionsResponse.items` 超过 3 条时校验失败。
4. `ResumeSessionResponse.resumeTo` 非法值时校验失败。
5. `SessionDetailResponse.status = question_refined` 时允许 `unloadDraft` 和 `resumeInfo` 同时存在。

---

## 8. 前端页面所需字段清单

## 8.1 首页

### 前端实现现状

当前 `HomeFeature.tsx` 首页包含以下需要后端数据的元素：

| UI 元素 | 位置 | 当前实现 | 需要的接口 |
|---|---|---|---|
| 用户头像 | 导航栏右侧 | `<div className="w-8 h-8 rounded-full ..." />` 灰色占位 | `GET /api/v1/users/me` → `avatarUrl` |
| "设置"链接 | 导航栏（齿轮图标） | `<Link href="#">设置</Link>` 指向 # | 需新建 `/settings` 路由，后端 `GET/PUT /api/v1/users/me/settings` |
| 示例问题 Chips | 提问区下方 | `t.raw('exampleQuestions')` i18n 写死 | 可选：`GET /api/v1/meta/example-questions` |
| "已守护 N 位旅人" | 底部状态栏 | 硬编码 `1,429` | `GET /api/v1/stats/global` → `totalUsersServed` |
| "探索中 / Exploring" 状态 | 底部状态栏 | 固定文案 | 可选：根据 `users/me` 的 `totalSessions` 动态化 |

### 必需接口

1. **`GET /api/v1/users/me`** — 导航栏头像、昵称
2. **`GET /api/v1/stats/global`** — 底部统计数据

### 可选接口

#### `GET /api/v1/meta/example-questions`

```json
{
  "items": [
    "为什么我总是下不了决心？",
    "我要不要离开现在的工作？",
    "这段关系让我感到疲惫，但……"
  ]
}
```

## 8.2 情绪识别页

字段：
- `emotionOptions[]`

### `GET /api/v1/meta/emotion-tags`

## 8.3 模式选择页

字段：
- `modeOptions[]`
- `recommendedMode`（可选）

## 8.4 结果页

字段：
- `question.text`
- `answer.answerText`
- `answer.hintText`
- `emotion.label`
- `insightMode.label`

## 8.5 卡片页

字段：
- `cards[].title`
- `cards[].description`
- `cards[].question`
- `cards[].psychologicalDimension`
- `cards[].isReverseCheck`

## 8.6 深度反思页

字段：
- `selectedCard.title`
- `selectedCard.question`
- `reflection.turns[]`
- `reflection.mode`

## 8.7 总结页

字段：
- `summary.summaryText`
- `summary.cognitiveBiases[]`
- `summary.futureSelf`
- `action.actionText`
- `action.actionReason`
- `action.tags[]`
- `action.ifThenPlan`

## 8.8 历史页

### 前端实现现状

当前 `HistoryFeature.tsx` 包含：
- 导航栏用户头像（同首页，依赖 `GET /api/v1/users/me`）
- 侧栏筛选器：时间范围（全部/近一周/近一月/近三月）、情绪标签（纠结/焦虑/迷茫/疲惫）
- 记录卡片：含标题、日期、模式徽章（illuminate/decisive）、彩色标签 pills
- "加载更多"分页按钮

### 每条记录字段

- `sessionId`
- `questionText`
- `createdAt`
- `insightMode` — 用于双色模式徽章（illuminate=amber, decisive=indigo）
- `selectedCardDimension`
- `actionType`
- `emotionTag`
- `saved`
- **`tags[]`** — 彩色标签数组，前端按 `color` 渲染不同 pill 样式
  ```json
  { "label": "反思维度：价值", "category": "dimension", "color": "gray" }
  ```
  color 枚举：`amber` | `blue` | `green` | `gray` | `red`

### 必需接口

1. **`GET /api/v1/sessions`** — 含 `tags[]` 字段
2. **`GET /api/v1/users/me`** — 导航栏头像

## 8.9 洞察页

字段：
- `summary`
- `themes[]`
- `emotions[]`
- `cardPreferences[]`
- `decisionStyle`

---

## 9. 错误处理与状态设计

## 9.1 推荐错误码

| 场景 | HTTP | 业务码 | 说明 |
|---|---|---|---|
| 输入为空/超长 | 400 | `INVALID_INPUT` | 参数错误 |
| 会话不存在 | 404 | `SESSION_NOT_FOUND` | ID 错误 |
| 状态不允许 | 409 | `INVALID_SESSION_STATE` | 比如未选卡就提交反思 |
| 命中高风险 | 422 | `RISK_BLOCKED` | 返回安全模板 |
| 频率受限 | 429 | `RATE_LIMITED` | 防刷 |
| AI 超时 | 504 | `AI_TIMEOUT` | 上游超时 |
| AI 输出不完整 | 502 | `INVALID_AI_PAYLOAD` | 可触发兜底 |
| 系统错误 | 500 | `INTERNAL_ERROR` | 通用异常 |

## 9.2 兜底策略

### 生成答案失败
返回兜底：
- answerText：也许你现在更需要先看清自己的状态。
- hintText：有些问题不是立刻回答，而是先分清情绪和事实。
- cards：通用 3 张卡

### 总结失败
返回兜底：
- summaryText：你现在最需要的，也许不是马上决定，而是让自己回到更清楚的位置。
- action：低风险澄清动作

---

## 10. 埋点建议

建议后端也落一份关键行为事件，便于和前端对账。

### 核心事件

- `session_draft_created`
- `soothing_viewed`
- `soothing_completed`
- `soothing_skipped`
- `unload_submitted`
- `question_refined`
- `emotion_selected`
- `emotion_skipped`
- `mode_selected`
- `answer_generated`
- `card_selected`
- `reflection_turn_submitted`
- `summary_generated`
- `action_adopted`
- `session_saved`
- `journal_note_saved`
- `followup_saved`
- `history_resume_clicked`
- `weekly_review_viewed`
- `risk_blocked`
- `session_failed`

### 推荐字段

```json
{
  "sessionId": "sess_01",
  "questionCategory": "career",
  "emotionTag": "tired",
  "emotionAfterTag": "clearer",
  "insightMode": "reflective",
  "soothingProgram": "breathing",
  "soothingDurationSeconds": 30,
  "questionSource": "free_text",
  "selectedCardDimension": "value",
  "actionType": "clarify",
  "actionStatus": "pending",
  "latencyMs": 1820
}
```

---

## 11. 与现有文档的一致性与补充点

### 11.1 与现有 PRD/开发文档一致的部分

以下方向与现有文档完全一致：
- 会话制接口
- 结构化 AI 输出
- 情绪识别入口
- 双模式触发
- 心理维度卡片
- 偏差提醒与未来自我
- 微实验与 If-Then
- 历史记录与模式洞察
- 安全拦截优先

### 11.2 基于当前效果图新增的后端补充

主要新增四点：

#### 1）增加 `draft → context_ready → answer_ready` 的阶段接口
因为当前页面把"提问 / 情绪 / 模式"拆成了连续步骤。

#### 2）将反思结构升级为 `turns[]`
因为当前 [UI_UX/deep_reflection.html](UI_UX/deep_reflection.html) 已经表现为多轮式反思，而不只是单次大输入框。

#### 3）新增 User Domain（用户、设置、全站统计）
前端首页导航栏已实现用户头像占位、"设置"入口链接，底部已硬编码"已守护 1,429 位旅人"统计文案。历史页导航栏同样包含头像。因此后端需补充：
- `GET /api/v1/users/me` — 头像与昵称
- `GET/PUT /api/v1/users/me/settings` — 偏好设置
- `GET /api/v1/stats/global` — 全站统计数据
- `POST /api/v1/users/me/avatar` — 头像上传

#### 4）历史记录响应补充 `tags[]` 字段
前端 `HistoryFeature.tsx` 中的 MOCK_RECORDS 数据包含 `tags: [{label, color}]` 数组，用于在每条记录卡片上渲染彩色标签 pills。后端 `GET /api/v1/sessions` 响应的 items 中需相应增加 `tags[]` 数组字段。

#### 5）补充“稳定入口 / 自由倾诉 / 情绪日记 / 回访补记”四类数据写入
因为当前设计已将这些页面纳入主链路，所以后端不应只在前端做临时态，而应提供：
- 稳定步骤的最小可追踪状态
- 自由倾诉原文与整理结果持久化
- 一句话情绪日记写入
- 历史回访补记与行动状态更新

这会让后端既兼容 MVP，又能平滑走向 Beta 的多轮深聊与用户体系。

---

## 12. 推荐实施优先级

## Phase 1：MVP 必做

1. `sessions/drafts`
2. `sessions/{id}/context`
3. `sessions/{id}/generate-answer`
4. `sessions/{id}/cards/{cardId}/select`
5. `sessions/{id}/reflection`
6. `sessions/{id}`
7. `sessions/{id}/save`
8. 风险检查与兜底

## Phase 2：MVP+

1. `actions/{actionId}/adopt`
2. `sessions/{id}/soothing`
3. `sessions/{id}/unload`
4. `sessions/{id}/journal-note`
5. `sessions/{id}/followup`
6. `users/{id}/journal/weekly-review`
2. 历史记录列表（含 `tags[]`）
3. **`GET /api/v1/users/me`** — 导航栏头像昵称
4. **`GET /api/v1/stats/global`** — 首页底部统计
5. 偏差提醒
6. 未来自我
7. If-Then 输出

## Phase 3：Beta

1. 模式洞察接口
2. 每日卡牌接口
3. 分享任务
4. 用户快照与长期画像
5. **`GET/PUT /api/v1/users/me/settings`** — 设置页
6. **`POST /api/v1/users/me/avatar`** — 头像上传
7. **`PATCH /api/v1/users/me`** — 个人信息编辑

---

## 13. 最终建议

如果只保留一句话作为后端设计原则：

> 把“照见一念”后端设计成一个 **结构化心理反思会话引擎**，而不是一个简单的问答 API。

具体落地上，最关键的 3 个点是：

1. **会话制**：所有页面围绕一个 `sessionId` 串联。
2. **分阶段**：情绪、模式、答案、反思、行动分别可追踪。
3. **结构化**：答案、卡片、偏差、未来自我、行动、洞察都必须是固定字段。

这样既能支撑当前原型，也能支撑后续真实 AI 编排、历史回看、模式分析和商业化扩展。
