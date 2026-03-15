# 照见一念（Glimmer）Mock / 真实接口切换规范 + 埋点事件清单

- 文档版本：V1.0
- 产出日期：2026-03-06
- 适用范围：Next.js Web 前端工程、MVP 到正式联调阶段
- 关联文档：
  - `docs/前端工程实施步骤-Nextjs-基于UIUX与后端接口.md`
  - `docs/后端接口与数据结构设计-基于UIUX原型.md`

---

## 1. 文档目标

这份文档解决两个问题：

1. **在后端尚未完成时，前端如何使用 Mock 数据推进开发，并在后端生效后自动切换到真实接口。**
2. **前端如何提前预留埋点事件结构、触发时机和字段，保证后续能与后端埋点体系对齐。**

一句话原则：

> 页面和组件永远不关心当前使用的是 Mock 还是 Live，也不关心埋点最终发到哪里；页面只调用统一业务方法和统一埋点方法。

---

## 2. 总体设计原则

### 2.1 数据源切换原则

前端必须支持 3 种运行模式：

1. **纯 Mock 模式**：本地开发、视觉还原、前端独立联调
2. **混合模式**：部分接口接真实后端，部分接口仍走 Mock
3. **纯 Live 模式**：测试 / 生产环境全部走真实接口

### 2.2 切换原则

切换发生在 **provider / repository 层**，而不是页面层。

页面禁止出现：
- `if (mockMode) { ... } else { ... }`
- 直接 import `mock.ts`
- 手动拼写假数据对象

### 2.3 埋点原则

埋点必须满足：

1. **事件名稳定**：和后端约定后不随意改动
2. **字段结构稳定**：新增字段尽量追加，不破坏旧结构
3. **触发点稳定**：统一在业务动作成功/失败的关键节点触发
4. **上报器可切换**：开发期可输出本地日志，联调和生产切到真实服务

---

## 3. 推荐目录结构

建议在前端工程中使用下面的结构：

```text
src/
├─ lib/
│  ├─ api/
│  │  ├─ client.ts
│  │  ├─ config.ts
│  │  ├─ repositories/
│  │  │  ├─ session.repository.ts
│  │  │  ├─ history.repository.ts
│  │  │  ├─ insights.repository.ts
│  │  │  ├─ daily-card.repository.ts
│  │  │  └─ safety.repository.ts
│  │  └─ providers/
│  │     ├─ http/
│  │     │  ├─ session.http.ts
│  │     │  ├─ history.http.ts
│  │     │  ├─ insights.http.ts
│  │     │  ├─ daily-card.http.ts
│  │     │  └─ safety.http.ts
│  │     └─ mock/
│  │        ├─ session.mock.ts
│  │        ├─ history.mock.ts
│  │        ├─ insights.mock.ts
│  │        ├─ daily-card.mock.ts
│  │        └─ safety.mock.ts
│  ├─ adapters/
│  │  ├─ session.adapter.ts
│  │  ├─ history.adapter.ts
│  │  ├─ insights.adapter.ts
│  │  └─ daily-card.adapter.ts
│  ├─ analytics/
│  │  ├─ events.ts
│  │  ├─ tracker.ts
│  │  └─ providers/
│  │     ├─ console.provider.ts
│  │     ├─ memory.provider.ts
│  │     └─ http.provider.ts
│  ├─ monitoring/
│  ├─ validators/
│  └─ constants/
├─ features/
└─ types/
```

---

## 4. 环境变量规范

建议使用下面这些环境变量。

## 4.1 数据源切换相关

```env
NEXT_PUBLIC_API_MODE=mock
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
NEXT_PUBLIC_ENABLE_MSW=true
```

### 含义

- `NEXT_PUBLIC_API_MODE=mock`
  - 所有仓储默认走 Mock Provider
- `NEXT_PUBLIC_API_MODE=live`
  - 所有仓储默认走真实 HTTP Provider
- `NEXT_PUBLIC_ENABLE_MSW=true`
  - 在浏览器开发环境中开启接口拦截模拟

## 4.2 混合模式建议

如果要做部分切换，建议增加更细的配置：

```env
NEXT_PUBLIC_API_MODE=hybrid
NEXT_PUBLIC_API_SESSION_PROVIDER=live
NEXT_PUBLIC_API_HISTORY_PROVIDER=mock
NEXT_PUBLIC_API_INSIGHTS_PROVIDER=mock
NEXT_PUBLIC_API_DAILY_CARD_PROVIDER=live
NEXT_PUBLIC_API_SAFETY_PROVIDER=live
```

这样可以做到：
- 主链路走真实接口
- 辅助页仍保留 Mock

## 4.3 埋点与监控相关

```env
NEXT_PUBLIC_ANALYTICS_MODE=console
NEXT_PUBLIC_ANALYTICS_ENDPOINT=https://api.example.com/analytics
NEXT_PUBLIC_MONITORING_MODE=console
NEXT_PUBLIC_SENTRY_DSN=
```

建议值：
- `console`：本地开发打印日志
- `memory`：测试环境暂存事件，方便调试
- `http`：正式上报给后端或第三方服务

---

## 5. Mock / Live 切换架构规范

## 5.1 标准调用链

统一采用下面的调用链：

```text
page / component
→ feature action
→ repository
→ provider(mock/http)
→ validator(zod)
→ adapter
→ tracker
→ UI render
```

### 各层职责

#### 页面层 `app/`
负责：
- 路由
- SEO metadata
- 页面拼装
- 加载态、错误态展示

不负责：
- 直接请求接口
- 直接判断 Mock / Live
- 直接写埋点请求

#### 业务层 `features/`
负责：
- 提交动作
- 页面流程编排
- 成功/失败后的页面跳转
- 调用 repository 和 tracker

#### 仓储层 `repositories/`
负责：
- 选择 provider
- 调用 validator 校验
- 调用 adapter 统一数据结构
- 对外暴露稳定方法

#### Provider 层 `providers/`
负责：
- Mock 数据返回或真实 HTTP 请求
- 不处理页面逻辑
- 不处理页面跳转

#### Adapter 层 `adapters/`
负责：
- 统一字段结构
- 兼容后端联调期临时字段变化
- 输出稳定前端模型

---

## 5.2 Repository 选择 Provider 的规则

建议采用如下优先级：

1. 读取域级 provider 配置，例如 `NEXT_PUBLIC_API_SESSION_PROVIDER`
2. 若没有域级配置，则读取全局 `NEXT_PUBLIC_API_MODE`
3. 若是本地开发且 provider 未设置，默认回退 `mock`

### 推荐策略

- 开发期：默认 `mock`
- 联调期：主链路 `live`，边缘功能 `mock`
- 测试期：尽量全 `live`
- 生产期：必须全 `live`

---

## 5.3 Mock 数据规范

Mock 数据必须满足以下要求。

### A. 返回值结构与后端一致

例如 `POST /api/v1/sessions/drafts` 的 Mock 返回必须包含：
- `sessionId`
- `status`
- `question`
- `nextStep`

不能返回另一套前端自定义命名。

### B. 支持正常流和异常流

每个关键接口至少准备以下 Mock 场景：

1. 成功返回
2. 参数错误
3. 风险拦截
4. 上游超时
5. 服务异常

### C. 支持延迟模拟

Mock 最好支持：
- 正常延迟：`300ms ~ 1200ms`
- 慢响应：`2s ~ 5s`

这样可以提前验证 loading 和防重复提交逻辑。

### D. 支持状态流转模拟

例如主会话链路需要支持：
- `draft`
- `context_ready`
- `answer_ready`
- `reflection_in_progress`
- `completed`
- `risk_blocked`
- `failed`

---

## 5.4 自动替换的具体规则

“后端生效后自动替换”在工程上指的是：

### A. 页面代码零修改

页面仍然调用：
- `sessionRepository.createDraft()`
- `sessionRepository.updateContext()`
- `sessionRepository.generateAnswer()`

而不是从：
- `session.mock.ts`
切换成
- `session.http.ts`

### B. 只改配置或装配层

切换时应该只改：
- 环境变量
- provider 注册逻辑
- API base URL

### C. Adapter 尽量吸收联调波动

当后端联调期字段发生微调时，应尽量由 adapter 兼容，而不是大面积修改页面组件。

---

## 6. 各业务域切换规范

## 6.1 会话域 `session`

### 对应接口
- `POST /api/v1/sessions/drafts`
- `PATCH /api/v1/sessions/{sessionId}/context`
- `POST /api/v1/sessions/{sessionId}/generate-answer`
- `GET /api/v1/sessions/{sessionId}`
- `POST /api/v1/sessions/{sessionId}/save`

### 切换建议
优先最早切 Live。

原因：
- 它是主链路入口
- `sessionId` 是整个产品流程主键
- 一旦真实接口可用，应尽快替换

## 6.2 反思域 `reflection`

### 对应接口
- `POST /api/v1/sessions/{sessionId}/cards/{cardId}/select`
- `POST /api/v1/sessions/{sessionId}/reflection`
- `POST /api/v1/sessions/{sessionId}/actions/{actionId}/adopt`

### 切换建议
第二优先级切 Live。

原因：
- 牵涉会话状态推进
- 多轮对话逻辑复杂
- 最需要尽早验证真实返回结构

## 6.3 历史域 `history`

### 对应接口
- `GET /api/v1/sessions`

### 切换建议
可在主链路稳定后再切。

## 6.4 洞察域 `insights`

### 对应接口
- `GET /api/v1/users/{userId}/insights/patterns`

### 切换建议
可后置，因为它不阻塞 MVP 主链路。

## 6.5 每日卡域 `daily-card`

### 对应接口
- `GET /api/v1/daily-cards/today`

### 切换建议
可独立切换，不影响主会话流程。

## 6.6 安全域 `safety`

### 对应接口
- `POST /api/v1/safety/check`

### 切换建议
必须尽早切 Live。

原因：
- 它涉及风险拦截
- 不应长期依赖 Mock 做真实安全判断

---

## 7. 联调阶段操作规范

## 7.1 联调顺序建议

建议按下面顺序接入真实接口：

1. `safety.check`
2. `sessions.drafts`
3. `sessions.context`
4. `sessions.generate-answer`
5. `sessions.get-detail`
6. `cards.select`
7. `reflection.submit`
8. `sessions.save`
9. `actions.adopt`
10. `sessions.list`
11. `insights.patterns`
12. `daily-cards.today`

## 7.2 联调时必须验证的事项

每个接口切 Live 时都要验证：

1. 状态码是否符合约定
2. 业务码是否符合约定
3. 字段是否完整
4. 空字段是否可容错
5. 超时场景是否有 fallback
6. 埋点是否仍正常触发
7. Mock / Live 切换后页面是否无感

## 7.3 联调期间禁止事项

禁止：
- 在页面中临时写死后端返回字段
- 直接跳过 repository 去写 `fetch`
- 为了赶进度删掉校验层
- 前端自行发明新的业务码含义

---

## 8. 埋点总体规范

## 8.1 埋点目标

埋点主要服务于 4 件事：

1. **流程漏斗分析**：用户卡在哪一步
2. **模型效果评估**：答案、卡片、反思、行动是否有效
3. **异常排查**：失败、超时、空结果、拦截原因
4. **前后端对账**：前端行为是否与后端日志一致
5. **商业化验证**：广告位是否被看见、点击、关闭，以及是否影响核心流程

## 8.2 埋点结构规范

每条事件建议包含两层：

### A. 公共字段

```json
{
  "eventName": "mode_selected",
  "eventVersion": "1.0.0",
  "timestamp": "2026-03-06T12:00:00Z",
  "pagePath": "/session/sess_01/mode",
  "sessionId": "sess_01",
  "userId": null,
  "requestId": "req_xxx",
  "source": "web",
  "env": "development"
}
```

### B. 业务字段

```json
{
  "insightMode": "reflective",
  "emotionTag": "tired",
  "questionCategory": "career"
}
```

### C. 性能字段（建议）

```json
{
  "latencyMs": 1820,
  "provider": "mock",
  "success": true
}
```

---

## 8.3 埋点上报模式

### 开发阶段
- 默认使用 `console.provider`
- 在浏览器控制台打印完整事件对象

### 测试阶段
- 可使用 `memory.provider`
- 便于在页面或测试脚本中读取事件列表

### 正式环境
- 使用 `http.provider`
- 发往后端埋点网关或第三方分析平台

---

## 9. 埋点事件清单

以下事件名优先与后端文档保持一致。

## 9.1 主链路事件

### 1）`soothing_viewed`

#### 触发时机
稳定入口页加载完成且核心卡片可见后触发。

#### 建议字段
- `sessionId`
- `entrySource`
- `defaultProgram`
- `provider`

---

### 2）`soothing_completed`

#### 触发时机
用户完成一次稳定步骤并成功写入会话上下文后触发。

#### 建议字段
- `sessionId`
- `selectedProgram`
- `selectedDurationSeconds`
- `entrySource`
- `provider`
- `latencyMs`

---

### 3）`soothing_skipped`

#### 触发时机
用户在稳定入口页点击跳过后触发。

#### 建议字段
- `sessionId`
- `entrySource`
- `skipStep`（固定为 `soothing`）
- `provider`

---

### 1）`session_draft_created`

#### 触发时机
首页成功创建草稿会话后触发。

#### 触发条件
- `POST /api/v1/sessions/drafts` 成功

#### 建议字段
- `sessionId`
- `questionCategory`
- `questionLength`
- `source`
- `riskPrecheckEnabled`
- `latencyMs`
- `provider`

---

### 4）`session_draft_created`

#### 触发时机
首页成功创建草稿会话后触发。

#### 触发条件
- `POST /api/v1/sessions/drafts` 成功

#### 建议字段
- `sessionId`
- `questionCategory`
- `questionLength`
- `source`
- `riskPrecheckEnabled`
- `latencyMs`
- `provider`

---

### 5）`unload_submitted`

#### 触发时机
用户在自由倾诉页提交原始表达并成功拿到整理结果后触发。

#### 建议字段
- `sessionId`
- `source`
- `rawTextLength`
- `hasVoiceTranscript`
- `provider`
- `latencyMs`

---

### 6）`question_refined`

#### 触发时机
自由倾诉内容被整理为标准问题后触发。

#### 建议字段
- `sessionId`
- `questionCategory`
- `refinementConfidence`
- `rawTextLength`
- `refinedQuestionLength`
- `provider`

---

### 7）`emotion_selected`

#### 触发时机
用户在情绪识别页点击继续，并成功提交情绪标签。

#### 建议字段
- `sessionId`
- `emotionTag`
- `emotionSource`（通常为 `user_selected`）
- `questionCategory`
- `latencyMs`
- `provider`

---

### 8）`emotion_skipped`

#### 触发时机
用户跳过情绪页时触发。

#### 建议字段
- `sessionId`
- `questionCategory`
- `skipStep`（固定为 `emotion`）
- `provider`

---

### 9）`mode_selected`

#### 触发时机
用户在模式页选中“照见模式”或“明断模式”并提交成功。

#### 建议字段
- `sessionId`
- `insightMode`
- `emotionTag`
- `questionCategory`
- `provider`
- `latencyMs`

---

### 10）`answer_generated`

#### 触发时机
启发答案与卡片成功返回后触发。

#### 建议字段
- `sessionId`
- `answerType`
- `emotionTag`
- `insightMode`
- `questionCategory`
- `cardsCount`
- `latencyMs`
- `provider`

---

### 11）`card_selected`

#### 触发时机
用户在思考卡片页选择某张卡片后触发。

#### 建议字段
- `sessionId`
- `cardId`
- `cardType`
- `psychologicalDimension`
- `isReverseCheck`
- `insightMode`
- `provider`

---

### 12）`reflection_turn_submitted`

#### 触发时机
用户在深度反思页提交一轮回答后触发。

#### 建议字段
- `sessionId`
- `selectedCardId`
- `reflectionMode`
- `turnCount`
- `replyLength`
- `finishReflection`
- `provider`
- `latencyMs`

---

### 13）`summary_generated`

#### 触发时机
总结与微实验生成成功后触发。

#### 建议字段
- `sessionId`
- `biasCount`
- `hasFutureSelf`
- `actionType`
- `actionTagCount`
- `provider`
- `latencyMs`

---

### 14）`action_adopted`

#### 触发时机
用户点击“带走行动”并采纳成功。

#### 建议字段
- `sessionId`
- `actionId`
- `actionType`
- `estimatedMinutes`
- `reversible`
- `provider`

---

### 15）`session_saved`

#### 触发时机
用户点击保存会话后触发。

#### 建议字段
- `sessionId`
- `saveSource`
- `status`
- `provider`

---

### 16）`journal_note_saved`

#### 触发时机
用户在总结页或历史页成功保存一句话情绪日记后触发。

#### 建议字段
- `sessionId`
- `journalNoteLength`
- `emotionAfterTag`
- `saveSource`
- `provider`

---

### 17）`followup_saved`

#### 触发时机
用户在历史页补记抽屉中成功保存回访内容后触发。

#### 建议字段
- `sessionId`
- `followupNoteLength`
- `actionStatus`
- `provider`

---

### 18）`history_resume_clicked`

#### 触发时机
用户在历史 / 情绪日记页点击“继续想想”或“恢复会话”时触发。

#### 建议字段
- `sessionId`
- `questionCategory`
- `fromPage`
- `provider`

---

### 19）`weekly_review_viewed`

#### 触发时机
周度情绪回看模块或独立页加载完成时触发。

#### 建议字段
- `weekStart`
- `weekEnd`
- `topEmotion`
- `unfinishedActions`
- `provider`

---

## 9.2 辅助页事件

### 20）`history_list_viewed`

#### 触发时机
历史列表加载成功后触发。

#### 建议字段
- `page`
- `pageSize`
- `resultCount`
- `keyword`
- `emotionTag`
- `emotionAfterTag`
- `insightMode`
- `category`
- `actionStatus`
- `hasFollowup`
- `provider`

---

### 21）`history_item_opened`

#### 触发时机
用户从历史列表进入某个会话详情。

#### 建议字段
- `sessionId`
- `questionCategory`
- `insightMode`
- `saved`

---

### 22）`followup_drawer_opened`

#### 触发时机
用户在历史页中打开补记抽屉时触发。

#### 建议字段
- `sessionId`
- `actionStatus`
- `hasExistingFollowup`

---

### 23）`pattern_insight_viewed`

#### 触发时机
模式洞察页加载完成。

#### 建议字段
- `userId`
- `sampleSize`
- `decisionStyleType`
- `provider`

---

### 24）`daily_card_viewed`

#### 触发时机
每日卡牌页面或今日卡片数据成功展示时触发。

#### 建议字段
- `cardId`
- `theme`
- `date`
- `provider`

---

### 25）`daily_card_shared`

#### 触发时机
用户点击分享按钮时触发。

#### 建议字段
- `cardId`
- `theme`
- `shareChannel`

---

## 9.3 广告与商业化事件

关联文档：

- [广告位配置与广告接入实施步骤.md](广告位配置与广告接入实施步骤.md)
- [广告位配置与广告接入研发Checklist.md](广告位配置与广告接入研发Checklist.md)
- [前端工程实施步骤-Nextjs-基于UIUX与后端接口.md](前端工程实施步骤-Nextjs-基于UIUX与后端接口.md)

### 26）`ad_slot_viewed`

#### 触发时机
广告位达到有效曝光条件后触发。

#### 建议字段
- `slotId`
- `slotType`
- `placement`
- `campaignId`
- `creativeId`
- `pagePath`
- `sessionId`
- `isSubscriber`
- `visibleRatio`
- `viewDurationMs`
- `provider`

#### 有效曝光建议
- 可见面积 ≥ 50%
- 持续可见 ≥ 1000ms
- 同一页面进入仅记 1 次有效曝光

---

### 27）`ad_clicked`

#### 触发时机
用户点击广告主体、CTA 或品牌合作卡片后触发。

#### 建议字段
- `slotId`
- `slotType`
- `placement`
- `campaignId`
- `creativeId`
- `targetUrl`
- `pagePath`
- `sessionId`
- `clickArea`
- `provider`

---

### 28）`ad_closed`

#### 触发时机
用户主动关闭或隐藏广告位后触发。

#### 建议字段
- `slotId`
- `slotType`
- `placement`
- `campaignId`
- `creativeId`
- `pagePath`
- `sessionId`
- `closeReason`
- `provider`

---

### 29）`reward_ad_started`

#### 触发时机
用户主动选择观看激励式广告以解锁权益时触发。

#### 建议字段
- `slotId`
- `placement`
- `rewardType`
- `unlockTarget`
- `pagePath`
- `sessionId`
- `provider`

---

### 30）`reward_ad_completed`

#### 触发时机
激励式广告完成播放且解锁成功后触发。

#### 建议字段
- `slotId`
- `placement`
- `rewardType`
- `unlockTarget`
- `grantSuccess`
- `pagePath`
- `sessionId`
- `provider`

---

## 9.4 安全与异常事件

### 31）`risk_blocked`

#### 触发时机
风险检查命中并进入安全分流时触发。

#### 建议字段
- `sessionId`（允许为空）
- `scene`
- `riskLevel`
- `hitPolicies`
- `blocked`
- `provider`

---

### 32）`session_failed`

#### 触发时机
会话主链路中的关键请求失败时触发。

#### 建议字段
- `sessionId`
- `step`
- `httpStatus`
- `businessCode`
- `provider`
- `latencyMs`
- `retryable`

---

### 33）`api_validation_failed`

#### 触发时机
接口返回结构不符合 `zod` 校验时触发。

#### 建议字段
- `apiName`
- `provider`
- `validationErrorCount`
- `sessionId`

---

### 34）`page_error_rendered`

#### 触发时机
页面进入错误态组件渲染时触发。

#### 建议字段
- `pagePath`
- `errorType`
- `sessionId`
- `recoverable`

---

## 10. 页面与埋点映射表

| 页面 | 关键动作 | 事件 |
|---|---|---|
| 稳定入口页 | 页面可见 | `soothing_viewed` |
| 稳定入口页 | 完成稳定步骤 | `soothing_completed` |
| 稳定入口页 | 跳过 | `soothing_skipped` |
| 首页 `/` | 创建草稿 | `session_draft_created` |
| 自由倾诉页 | 提交原始表达 | `unload_submitted` |
| 自由倾诉页 | 生成整理后问题 | `question_refined` |
| 情绪页 | 选择情绪 | `emotion_selected` |
| 情绪页 | 跳过 | `emotion_skipped` |
| 模式页 | 选择模式 | `mode_selected` |
| 结果页 | 成功拿到答案 | `answer_generated` |
| 卡片页 | 选择卡片 | `card_selected` |
| 反思页 | 提交一轮回答 | `reflection_turn_submitted` |
| 总结页 | 成功出总结 | `summary_generated` |
| 总结页 | 采纳行动 | `action_adopted` |
| 总结页 | 保存会话 | `session_saved` |
| 总结页 / 历史页 | 保存一句话日记 | `journal_note_saved` |
| 历史页 | 查看列表 | `history_list_viewed` |
| 历史页 | 打开某条记录 | `history_item_opened` |
| 历史页 | 打开补记抽屉 | `followup_drawer_opened` |
| 历史页 | 保存回访补记 | `followup_saved` |
| 历史页 | 继续恢复会话 | `history_resume_clicked` |
| 历史页 / 周度回看页 | 查看周度回看 | `weekly_review_viewed` |
| 洞察页 | 查看洞察 | `pattern_insight_viewed` |
| 每日卡页 | 查看卡牌 | `daily_card_viewed` |
| 每日卡页 | 点击分享 | `daily_card_shared` |
| 结果页 / 总结页 / 历史页 / 每日卡页 | 广告有效曝光 | `ad_slot_viewed` |
| 结果页 / 总结页 / 历史页 / 每日卡页 | 点击广告 | `ad_clicked` |
| 结果页 / 历史页 / 每日卡页 | 关闭广告 | `ad_closed` |
| 激励式广告入口页 | 开始观看激励广告 | `reward_ad_started` |
| 激励式广告入口页 | 完成激励广告 | `reward_ad_completed` |
| 风险流程 | 风险命中 | `risk_blocked` |
| 全链路 | 请求失败 | `session_failed` |

---

## 11. 埋点触发最佳实践

## 11.1 成功事件只在“真正成功”后触发

例如：
- `mode_selected` 应在接口成功更新上下文后触发
- 而不是用户仅仅点了模式卡片就触发

## 11.2 页面展示事件只在“数据可见”后触发

例如：
- `history_list_viewed` 应在列表成功渲染时触发
- 而不是请求一发出就触发
- `ad_slot_viewed` 应在广告位满足有效曝光条件后触发，而不是广告组件刚挂载就触发

## 11.3 失败事件要带上下文

失败事件至少带：
- 当前步骤
- 会话 ID
- HTTP 状态码
- 业务码
- 是否可重试

## 11.4 避免重复上报

需要防止：
- 重复点击按钮导致重复成功埋点
- 页面刷新导致同一展示事件多次上报
- 重试请求把失败/成功事件重复打乱

建议做：
- 提交按钮禁用
- 页面级去重标记
- requestId 关联

---

## 12. 与监控系统的边界

埋点和错误监控不是同一件事。

### 埋点更关心
- 用户行为
- 产品流程
- 业务转化

### 监控更关心
- 前端异常
- JS 报错
- 接口超时
- 性能问题

建议：
- `track()` 负责行为事件
- `captureException()` 负责错误监控

两者可以在某些失败场景同时触发，但不要混成一个系统。

---

## 13. 实施顺序建议

## 第一步：先搭切换框架

优先完成：
- 环境变量
- repository/provider 分层
- Mock provider
- console analytics provider

## 第二步：主链路先用 Mock 跑通

优先覆盖：
- 草稿创建
- 情绪更新
- 模式更新
- 生成答案
- 选卡
- 反思提交
- 总结展示

## 第三步：接入真实安全与主链路接口

优先切：
- `safety`
- `session`
- `reflection`

## 第四步：接入真实埋点上报

先不改事件名和事件字段，只切 provider。

## 第五步：补历史、洞察、每日卡

这些可以在主链路稳定后接入。

---

## 14. 最终规范总结

如果把这份文档压缩成一句话：

> Mock 和真实接口的切换必须发生在 repository/provider 层，页面层零感知；埋点事件要从第一天就按稳定事件名和稳定字段结构落位，等后端生效后只替换 provider，不替换业务代码。

对这个项目来说，最关键的不是“先把所有接口都连上”，而是：

1. 先把切换架构搭对
2. 先把事件结构定义对
3. 再逐步接入真实后端

这样才能保证后面联调不会推翻前面的前端工作。
