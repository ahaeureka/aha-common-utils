# 照见一念（Glimmer）广告位配置与广告接入研发 Checklist

- 文档版本：V1.0
- 产出日期：2026-03-06
- 适用范围：前端研发 / 联调 / 商业化验证阶段
- 阅读角色：前端、全栈、数据、测试、AI 编程 Agent
- 关联文档：
  - [广告位配置与广告接入实施步骤.md](广告位配置与广告接入实施步骤.md)
  - [广告商业化产品方案与页面规划.md](广告商业化产品方案与页面规划.md)
  - [广告商业化接口契约草案.md](广告商业化接口契约草案.md)
  - [前端工程实施步骤-Nextjs-基于UIUX与后端接口.md](前端工程实施步骤-Nextjs-基于UIUX与后端接口.md)
  - [Mock与真实接口切换规范-埋点事件清单.md](Mock与真实接口切换规范-埋点事件清单.md)
  - [UIUX设计文档-AI答案机.md](UIUX设计文档-AI答案机.md)

---

## 1. 文档定位

这是一份给研发和 AI 编程 Agent 使用的执行清单。

用途：

- 防止广告接入只做了 UI，没有做埋点
- 防止只接了 SDK，没有做频控与会员判断
- 防止只做了代码，没有回写文档和验证清单

建议阅读顺序：

1. [广告位配置与广告接入实施步骤.md](广告位配置与广告接入实施步骤.md)
2. [本文件：广告位配置与广告接入研发Checklist.md](广告位配置与广告接入研发Checklist.md)
3. [广告商业化接口契约草案.md](广告商业化接口契约草案.md)
4. [Mock与真实接口切换规范-埋点事件清单.md](Mock与真实接口切换规范-埋点事件清单.md)

---

## 2. 研发实施 Checklist

## 2.1 产品与设计输入确认

- [ ] 已确认允许投放广告的页面
- [ ] 已确认禁止投放广告的页面
- [ ] 已确认每个广告位的 `placement`
- [ ] 已确认每个广告位的 `slotType`
- [ ] 已确认每个广告位的 `labelType`
- [ ] 已确认会员去广告规则
- [ ] 已确认是否支持激励式广告
- [ ] 已确认广告关闭规则与频控规则

---

## 2.2 文档与命名对齐

- [ ] PRD 已包含广告商业化描述
- [ ] UI/UX 文档已包含广告位预留原则
- [ ] 前端实施文档已包含广告容器与广告埋点要求
- [ ] 埋点规范文档已包含广告事件名与字段
- [ ] 广告位命名与代码中的 `placement` 一致
- [ ] 广告位命名与埋点中的 `placement` 一致

---

## 2.3 代码结构检查

当前建议代码路径：

- [glimmer-web/components/ads/ad-slot.tsx](../glimmer-web/components/ads/ad-slot.tsx)
- [glimmer-web/components/ads/sponsored-card.tsx](../glimmer-web/components/ads/sponsored-card.tsx)
- [glimmer-web/lib/ads/config.ts](../glimmer-web/lib/ads/config.ts)
- [glimmer-web/lib/analytics/ad-events.ts](../glimmer-web/lib/analytics/ad-events.ts)
- [glimmer-web/lib/analytics/events.ts](../glimmer-web/lib/analytics/events.ts)

Checklist：

- [ ] 已存在统一广告容器组件
- [ ] 已存在品牌合作卡组件
- [ ] 已存在广告位配置中心
- [ ] 已存在广告事件辅助函数
- [ ] 已存在曝光规则解析函数
- [ ] 已存在会员可见性判断逻辑

---

## 2.4 广告位配置检查

每个广告位应至少具备：

- [ ] `slotId`
- [ ] `slotType`
- [ ] `placement`
- [ ] `labelType`
- [ ] `closable`
- [ ] `enabled`
- [ ] `subscriberVisible`
- [ ] `impressionRules`
- [ ] 激励位已补 `rewardType`

建议检查当前预留位：

- [ ] `result_bottom`
- [ ] `summary_bottom`
- [ ] `history_feed`
- [ ] `daily_card_inline`
- [ ] `reward_unlock`

---

## 2.5 页面挂载检查

### 结果页
- [ ] 广告位在主内容之后
- [ ] 不影响“继续反思”主按钮
- [ ] 曝光后可触发 `ad_slot_viewed`

### 总结页
- [ ] 广告位在总结与行动建议之后
- [ ] 不伪装成 AI 行动建议
- [ ] 点击后可触发 `ad_clicked`

### 历史页
- [ ] 广告位以低频信息流形式出现
- [ ] 不伪装成用户真实历史
- [ ] 滚动曝光不重复上报

### 每日卡牌页
- [ ] 广告位与分享区视觉分离
- [ ] 明确标识品牌合作
- [ ] 点击与关闭可单独埋点

### 激励式入口
- [ ] 必须由用户主动触发
- [ ] 明确展示解锁权益
- [ ] 已处理成功 / 失败 / 中断回调

---

## 2.6 埋点检查

最少事件：

- [ ] `ad_slot_viewed`
- [ ] `ad_clicked`
- [ ] `ad_closed`
- [ ] `reward_ad_started`
- [ ] `reward_ad_completed`
- [ ] `sponsored_card_opened`

字段检查：

- [ ] `slotId`
- [ ] `slotType`
- [ ] `placement`
- [ ] `pagePath`
- [ ] `sessionId`（如适用）
- [ ] `campaignId`
- [ ] `creativeId`
- [ ] `isSubscriber`

有效曝光检查：

- [ ] 未在组件挂载时直接记曝光
- [ ] 已使用 `IntersectionObserver` 或等效方案
- [ ] 满足可见比例阈值
- [ ] 满足停留时长阈值
- [ ] 同页去重逻辑已生效

---

## 2.7 Provider / Adapter 预留检查

如果尚未接真实广告平台，也应先保证分层正确：

- [ ] 页面未直接依赖广告平台 SDK
- [ ] 广告平台逻辑可被替换
- [ ] 已预留 `providers/` 或等价层
- [ ] 已预留 `repositories/` 或等价层
- [ ] Mock 广告数据可独立验证 UI 与埋点

---

## 2.8 测试与验收 Checklist

### 功能
- [ ] 广告位可正常展示
- [ ] 关闭按钮有效
- [ ] CTA 有反馈
- [ ] 会员用户符合去广告规则

### 埋点
- [ ] 曝光事件口径正确
- [ ] 点击事件不重复
- [ ] 关闭事件只在主动关闭时触发
- [ ] 激励完成事件能区分成功与失败

### 体验
- [ ] 页面无明显布局跳动
- [ ] 广告位与内容视觉边界清晰
- [ ] 不影响主路径转化
- [ ] 无明显误触问题

### 工程
- [ ] 代码已通过类型检查
- [ ] 新增文件已补导出
- [ ] 文档链接已更新
- [ ] 相关实现已回写到实施文档

---

## 3. AI 编程 Agent 执行提示

如果你是 AI 编程 Agent，修改广告相关代码时建议同步检查：

- [前端工程实施步骤-Nextjs-基于UIUX与后端接口.md](前端工程实施步骤-Nextjs-基于UIUX与后端接口.md)
- [Mock与真实接口切换规范-埋点事件清单.md](Mock与真实接口切换规范-埋点事件清单.md)
- [广告位配置与广告接入实施步骤.md](广告位配置与广告接入实施步骤.md)
- [广告商业化接口契约草案.md](广告商业化接口契约草案.md)
- [本文件：广告位配置与广告接入研发Checklist.md](广告位配置与广告接入研发Checklist.md)

提交前至少确认：

- [ ] 文档和代码的 `placement` 名称一致
- [ ] 新增广告位已补埋点
- [ ] 新增埋点已补文档
- [ ] 会员与非会员逻辑已考虑

---

## 4. 一句话结论

> 广告接入的最低标准不是“页面能看到一个广告位”，而是“配置、渲染、埋点、频控、会员逻辑、文档引用”全部闭环。
