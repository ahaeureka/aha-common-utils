# 照见一念（Glimmer）：面向开发的功能拆解版

- 基于文档：[主 PRD：照见一念（Glimmer）](docs/PRD-AI%E7%AD%94%E6%A1%88%E6%9C%BA.md)
- 文档版本：V1.0
- 日期：2026-03-06
- 目标：将 PRD 转换为可供产品、前端、后端、AI、测试协作执行的开发拆解文档

---

## 1. 开发目标

MVP 版本仅实现一条完整主链路：

```text
输入问题
→ 生成启发式答案
→ 生成 3 张思考卡片
→ 用户选择 1 张卡片并回答
→ 生成反思总结
→ 生成微行动建议
→ 保存结果
```

本阶段目标不是做完整“AI 心理产品”，而是优先验证：

1. 用户是否愿意输入真实问题
2. 用户是否愿意进入卡片反思
3. AI 输出是否足够有启发
4. 产品链路是否稳定可复用

---

## 2. 开发范围

## 2.1 本期开发范围（MVP）

### 用户侧

- 首页输入问题
- 查看 AI 启发式答案
- 查看 3 张思考卡片
- 选择 1 张卡片进入深入提问
- 输入回答
- 查看 AI 反思总结
- 查看 AI 微行动建议
- 保存本次结果
- 再问一次

### 系统侧

- 问题分类
- Prompt 编排
- 结果结构化返回
- 敏感内容基础拦截
- 提问记录持久化
- 埋点日志记录

### 管理/内部侧

- 基础日志追踪
- 模型请求失败兜底
- 结果重试机制

## 2.2 本期不开发

- 登录注册复杂体系
- 分享海报生成
- 多轮深聊
- 历史趋势分析展示
- 每日卡牌
- 付费订阅
- 用户画像中心
- 后台运营系统

---

## 3. 系统模块拆解

MVP 建议拆为 6 个模块：

1. 前端交互模块
2. 会话与状态管理模块
3. AI 编排模块
4. 内容安全模块
5. 数据存储模块
6. 埋点与日志模块

---

## 4. 前端功能拆解

## 4.1 页面结构

### 页面 1：首页 `AskPage`

#### 功能

- 展示产品标题、副标题
- 输入问题
- 点击开始按钮
- 前端校验输入内容
- 发起生成请求

#### 组件拆解

- `QuestionInput`
- `PrimaryButton`
- `ExampleQuestions`
- `LoadingOverlay`
- `ErrorToast`

#### 输入规则

- 最短长度：建议 2 个字符
- 最长长度：建议 200–300 个字符
- 去除纯空格

#### 状态

- idle
- typing
- submitting
- error

#### 验收

- 空输入不可提交
- 提交后展示加载态
- 请求成功进入结果页
- 请求失败给出可重试提示

---

### 页面 2：答案结果页 `AnswerPage`

#### 功能

- 展示启发式答案
- 展示补充提示
- 展示继续反思入口
- 支持“重新提问”

#### 组件拆解

- `AnswerCard`
- `HintBlock`
- `ContinueReflectionButton`
- `AskAgainButton`

#### 数据字段

- `answerText`
- `hintText`
- `answerType`
- `questionText`

#### 验收

- 页面可回显原问题
- 结果结构固定展示
- 无卡片数据时不可继续下一步

---

### 页面 3：思考卡片页 `ReflectionCardsPage`

#### 功能

- 展示 3 张卡片
- 允许用户选择 1 张
- 进入卡片深问页

#### 组件拆解

- `ReflectionCardList`
- `ReflectionCard`
- `SelectCardButton`

#### 数据字段

每张卡片：

- `cardId`
- `cardType`
- `title`
- `description`
- `question`

#### 交互规则

- 仅允许单选
- 点击整张卡片或按钮均可进入下一步

#### 验收

- 必须固定返回 3 张卡片
- 卡片展示顺序可随机
- 用户所选卡片需被记录

---

### 页面 4：深度提问页 `ReflectionReplyPage`

#### 功能

- 展示所选卡片问题
- 用户填写回答
- 提交回答后生成总结与行动建议

#### 组件拆解

- `SelectedCardHeader`
- `ReflectionQuestionBlock`
- `ReplyTextarea`
- `SubmitReflectionButton`
- `InlineLoading`

#### 输入规则

- 最短长度建议：1 个字符
- 最长长度建议：500–1000 个字符
- 支持用户跳过回答（可选）

#### 状态

- idle
- typing
- submitting
- error

#### 验收

- 用户回答可提交
- 提交后按钮禁用防重复提交
- 提交成功跳转结果页

---

### 页面 5：总结与行动页 `ActionPage`

#### 功能

- 展示 AI 总结
- 展示 1 个微行动建议
- 展示行动建议解释
- 支持“保存结果”“再问一次”

#### 组件拆解

- `SummaryCard`
- `ActionSuggestionCard`
- `SaveSessionButton`
- `AskAgainButton`

#### 数据字段

- `reflectionSummary`
- `actionText`
- `actionReason`
- `actionType`

#### 验收

- 总结和行动建议必须同时出现
- 页面支持保存成功反馈
- 再问一次会清空当前会话状态

---

## 5. 前端状态管理拆解

建议建立单次问答会话对象：`session`

### 5.1 会话字段

```ts
interface AskSession {
  sessionId: string;
  questionText: string;
  questionCategory?: string;
  answer?: {
    answerText: string;
    hintText: string;
    answerType: string;
  };
  cards?: ReflectionCard[];
  selectedCardId?: string;
  reflectionReply?: string;
  reflectionSummary?: string;
  action?: {
    actionText: string;
    actionReason: string;
    actionType: string;
  };
  status: 'idle' | 'answer_ready' | 'card_ready' | 'submitted' | 'completed' | 'error';
}
```

### 5.2 状态流转

```text
idle
→ submit_question
→ answer_ready
→ card_ready
→ submit_reflection
→ completed
```

### 5.3 前端异常处理

- 请求超时
- 结构化字段缺失
- AI 内容为空
- 用户重复提交
- 页面刷新导致状态丢失

### 5.4 建议

- MVP 可先使用前端内存状态 + localStorage 恢复
- 若已有全局状态库，可接入 `Zustand` / `Redux Toolkit`

---

## 6. 后端接口拆解

建议按“会话制”设计接口，便于后续扩展多轮对话与历史记录。

## 6.1 创建问题并生成首轮结果

### 接口

`POST /api/v1/sessions`

### 入参

```json
{
  "questionText": "我要不要换工作？"
}
```

### 处理逻辑

1. 校验输入
2. 创建 `session`
3. 识别问题分类
4. 调用 Trigger Engine 生成答案
5. 调用 Reflection Engine 生成 3 张卡片
6. 保存结构化结果
7. 返回前端

### 返回

```json
{
  "sessionId": "sess_xxx",
  "question": {
    "text": "我要不要换工作？",
    "category": "career"
  },
  "answer": {
    "answerText": "试探比冲动更适合现在的你。",
    "hintText": "你也许不需要立刻离开，而是先验证外部机会。",
    "answerType": "action_probe"
  },
  "cards": [
    {
      "cardId": "card_1",
      "cardType": "worst_case",
      "title": "最坏情况",
      "description": "先看代价，再判断是否真的不可承受。",
      "question": "如果这次变化不如预期，最坏会怎样？"
    }
  ]
}
```

### 错误码建议

- `400` 参数错误
- `429` 请求频率超限
- `500` 生成失败

---

## 6.2 提交反思回答并生成总结/行动

### 接口

`POST /api/v1/sessions/{sessionId}/reflection`

### 入参

```json
{
  "selectedCardId": "card_2",
  "replyText": "我其实不知道下一份工作想做什么，只是现在太累了。"
}
```

### 处理逻辑

1. 校验 `sessionId`
2. 校验 `selectedCardId` 属于当前会话
3. 调用 Reflection Engine 生成总结
4. 调用 Action Engine 生成行动建议
5. 保存结果
6. 返回前端

### 返回

```json
{
  "sessionId": "sess_xxx",
  "reflection": {
    "summary": "你现在更强烈的动力来自对现状的消耗感，而不是明确的新方向。"
  },
  "action": {
    "actionText": "这周花 30 分钟写下你下一份工作必须满足的 3 个条件。",
    "actionReason": "先定义方向，比马上离开现状更重要。",
    "actionType": "self_clarify"
  }
}
```

---

## 6.3 获取单次会话详情

### 接口

`GET /api/v1/sessions/{sessionId}`

### 用途

- 页面刷新后恢复结果
- 后续接历史记录

---

## 6.4 保存/完成会话

### 接口

`POST /api/v1/sessions/{sessionId}/save`

### 用途

- 标记用户主动保存
- 为后续历史记录与收藏做准备

---

## 7. AI 编排模块拆解

## 7.1 AI 模块划分

建议拆成 3 个服务：

- `triggerService`
- `reflectionService`
- `actionService`

每个服务输出固定 JSON 结构，禁止前端直接依赖自然语言裸文本。

---

## 7.2 Trigger Service

### 输入

- 问题文本
- 问题分类
- 可选情绪标签

### 输出结构

```json
{
  "answerText": "...",
  "hintText": "...",
  "answerType": "..."
}
```

### 规则

- 字数控制
- 不使用绝对判断
- 不出现高风险直接建议
- 尽量留有解释空间

### 可配置策略

- `action_probe`
- `delay`
- `observe`
- `emotion_check`
- `value_check`
- `time_perspective`

---

## 7.3 Reflection Service

### 输入

- 问题文本
- 问题分类
- Trigger 输出

### 输出结构

```json
{
  "cards": [
    {
      "cardId": "card_1",
      "cardType": "future_self",
      "title": "五年视角",
      "description": "把时间拉长，重新看今天。",
      "question": "五年后回看，你更可能后悔什么？"
    }
  ]
}
```

### 规则

- 固定返回 3 张卡片
- 卡片类型不能重复
- 卡片标题、解释、问题必须成组
- 问题尽量避免是非题

---

## 7.4 Reflection Summary Service

### 输入

- 问题文本
- 选中卡片
- 用户回答

### 输出结构

```json
{
  "summary": "..."
}
```

### 规则

- 不机械复述用户原话
- 需要给出“你更在意的是/你真正担心的是”式总结
- 长度控制在 1–3 句

---

## 7.5 Action Service

### 输入

- 问题文本
- 选中卡片类型
- 用户回答
- 反思总结

### 输出结构

```json
{
  "actionText": "...",
  "actionReason": "...",
  "actionType": "self_clarify"
}
```

### 规则

- 微行动时间成本不超过 1 小时
- 不建议高风险不可逆操作
- 要优先给信息收集、澄清、低成本试探类建议

---

## 8. 内容安全模块拆解

## 8.1 输入审核

需要识别以下高风险输入：

- 自伤、自杀倾向
- 伤害他人
- 极端暴力
- 严重精神危机场景
- 医疗/法律/投资等专业咨询

### 处理方式

- 不进入常规答案流程
- 返回安全提示模板
- 记录安全事件日志

---

## 8.2 输出审核

对 AI 输出做二次校验，重点拦截：

- “你必须马上……”
- “立刻分手/辞职/断联”
- 明确医学判断
- 暗示绝望、羞耻、自责的表达
- 高风险不可逆行动建议

### 实现建议

- 规则词库 + LLM 自检双层校验
- 不合规则自动重试一次
- 超过重试次数返回兜底文案

---

## 8.3 兜底文案

当生成失败或校验失败时返回通用安全结果：

- 启发答案兜底
- 通用卡片兜底
- 通用行动建议兜底

示例：

- 答案：也许你现在更需要先看清自己的状态。
- 提示：有些问题不是立刻回答，而是先分清情绪和事实。

---

## 9. 数据库拆解

## 9.1 表一：`sessions`

字段建议：

- `id`
- `user_id` 可空
- `question_text`
- `question_category`
- `question_emotion_tag`
- `status`
- `created_at`
- `updated_at`

## 9.2 表二：`session_answers`

- `id`
- `session_id`
- `answer_type`
- `answer_text`
- `hint_text`
- `model_name`
- `raw_payload`
- `created_at`

## 9.3 表三：`session_cards`

- `id`
- `session_id`
- `card_id`
- `card_type`
- `title`
- `description`
- `question_text`
- `display_order`

## 9.4 表四：`session_reflections`

- `id`
- `session_id`
- `selected_card_id`
- `reply_text`
- `summary_text`
- `created_at`

## 9.5 表五：`session_actions`

- `id`
- `session_id`
- `action_type`
- `action_text`
- `action_reason`
- `created_at`

## 9.6 表六：`event_logs`

- `id`
- `session_id`
- `event_name`
- `event_payload`
- `created_at`

---

## 10. 埋点拆解

MVP 至少埋以下事件：

### 页面与行为事件

- `ask_page_view`
- `question_submit_click`
- `question_submit_success`
- `question_submit_fail`
- `answer_page_view`
- `reflection_cards_view`
- `reflection_card_click`
- `reflection_submit_click`
- `reflection_submit_success`
- `reflection_submit_fail`
- `action_page_view`
- `session_save_click`
- `ask_again_click`

### 数据属性建议

- `sessionId`
- `questionCategory`
- `answerType`
- `selectedCardType`
- `actionType`
- `latencyMs`
- `resultStatus`

---

## 11. 测试拆解

## 11.1 前端测试

### 核心用例

- 空输入提交
- 超长输入提交
- 网络失败重试
- 提交中重复点击
- 卡片选择与跳转
- 页面刷新恢复

## 11.2 后端测试

### 核心用例

- 创建会话成功
- 问题分类为空时兜底
- AI 返回字段缺失时兜底
- 非法 `sessionId` 提交反思
- 非法 `cardId` 提交反思
- 保存接口重复调用

## 11.3 AI 输出测试

需建立样例集覆盖：

- 职业类问题
- 关系类问题
- 生活选择类问题
- 情绪迷茫类问题
- 边界模糊输入
- 高风险输入

重点检查：

- 风格稳定性
- 结构完整性
- 安全合规性
- 重复率

---

## 12. 开发任务拆分建议

## 12.1 前端任务

### FE-01 首页搭建

- 输入框
- 按钮
- 校验
- Loading
- 错误提示

### FE-02 结果页搭建

- 答案展示
- 提示展示
- 再问一次

### FE-03 卡片页搭建

- 卡片列表
- 选中交互
- 跳转

### FE-04 回答页搭建

- 输入框
- 提交逻辑
- 防重复提交

### FE-05 总结与行动页搭建

- 总结展示
- 行动建议展示
- 保存结果

### FE-06 会话状态管理

- session store
- 本地恢复
- 页面守卫

---

## 12.2 后端任务

### BE-01 会话创建接口

- 建表
- 参数校验
- 创建 session

### BE-02 AI 编排接口

- Trigger 调用
- Reflection Cards 调用
- 结构化返回

### BE-03 反思提交接口

- 校验会话和卡片
- 生成总结和行动
- 持久化

### BE-04 保存接口与会话详情接口

- 查询单次结果
- 保存标记

### BE-05 错误兜底与日志

- 异常捕获
- 日志记录
- 超时处理

---

## 12.3 AI/算法任务

### AI-01 问题分类器

- career
- relationship
- life
- emotion
- other

### AI-02 Trigger Prompt 模板

- 6 类回答风格模板
- 固定 JSON 输出

### AI-03 Reflection Cards Prompt 模板

- 8 类卡片维度池
- 去重策略

### AI-04 Reflection Summary Prompt 模板

- 基于回答的总结模板
- 控制长度与语气

### AI-05 Action Prompt 模板

- 微行动类型池
- 风险控制规则

### AI-06 安全规则与兜底文案

- 输入拦截
- 输出校验
- 失败重试

---

## 12.4 QA 任务

### QA-01 主链路冒烟测试

### QA-02 异常场景测试

### QA-03 高风险内容测试

### QA-04 埋点校验

### QA-05 多端适配测试

---

## 13. 推荐开发顺序

建议按以下顺序推进：

### 第 1 阶段：链路打通

1. 首页输入
2. 创建会话接口
3. 返回 mock 答案 + mock 卡片
4. 卡片选择
5. 提交回答
6. 返回 mock 总结 + mock 行动

### 第 2 阶段：接入真实 AI

1. Trigger Engine
2. Reflection Engine
3. Summary + Action Engine
4. 结构化校验

### 第 3 阶段：稳定性补齐

1. 安全策略
2. 兜底逻辑
3. 埋点
4. 保存会话
5. 页面恢复

---

## 14. 风险点与开发注意事项

### 14.1 结构化输出风险

风险：AI 返回字段不完整，导致前端不可渲染。

建议：

- 后端统一做 JSON 校验
- 缺字段时自动补兜底值
- 前端不直接依赖原始模型输出

### 14.2 输出过空泛

风险：用户觉得像普通鸡汤。

建议：

- 引入问题分类
- 控制卡片维度差异化
- 对总结模板做强约束

### 14.3 高风险问题误处理

风险：把危机问题当普通问题处理。

建议：

- 输入前置检测
- 风险问题单独模板
- 记录安全命中率

### 14.4 前端状态断裂

风险：刷新页面后链路丢失。

建议：

- 按 `sessionId` 查询结果恢复
- 本地缓存最后一次会话 id

---

## 15. 交付物定义

开发完成后应至少交付：

### 前端

- 可运行的 MVP 页面链路
- 基础状态管理
- 错误与加载态

### 后端

- 4 个核心接口
- 数据库表结构
- AI 编排服务
- 日志与异常处理

### AI

- 可版本化的 Prompt 模板
- 输出 JSON 规范
- 兜底内容集
- 安全规则清单

### QA

- 用例清单
- 冒烟报告
- 风险场景验证报告

---

## 16. 建议的里程碑

### 里程碑 1：页面与 Mock 流程可跑

目标：产品链路可演示

### 里程碑 2：真实 AI 输出接入

目标：用户可完成完整体验

### 里程碑 3：安全与埋点完善

目标：可灰度测试

### 里程碑 4：MVP 发布

目标：开始收集真实用户数据

---

## 17. 一句话总结

> 对开发而言，MVP 的核心不是“做一个会聊天的 AI”，而是搭出一条稳定、可控、可追踪的结构化决策反思链路。
