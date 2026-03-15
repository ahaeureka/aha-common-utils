# 照见一念（Glimmer）SEO 实施规范 + metadata / 分享页 / 结构化数据清单

- 文档版本：V1.0
- 产出日期：2026-03-06
- 适用范围：Next.js Web 首发、SEO 与分享传播建设
- 关联文档：
  - `docs/前端研发执行总方案.md`
  - `docs/前端技术选型方案-照见一念.md`
  - `docs/后端接口与数据结构设计-基于UIUX原型.md`

---

## 1. 文档目标

这份文档用于明确：

1. 哪些页面要重点做 SEO
2. Next.js 中 `metadata` 应该如何组织
3. 分享页应该如何设计与路由化
4. 结构化数据 Schema 应如何预留
5. 上线前 SEO 应该检查什么

一句话原则：

> SEO 不是上线前最后补的文案工作，而是从路由设计、渲染方式、metadata、分享页到结构化数据一起规划的工程能力。

---

## 2. SEO 总体策略

基于产品形态，SEO 要分成两类页面处理。

## 2.1 强 SEO 页面

这类页面承担搜索流量、品牌传播或社交分享传播，应优先使用服务端渲染或静态生成，并完整配置 `metadata`。

建议包括：

- 首页 `/`
- 品牌落地页 / 内容页
- 分享结果页 `/share/session/[id]`
- 每日卡分享页 `/share/daily-card/[date]`
- 可公开、脱敏的洞察页 `/share/insight/[id]`

## 2.2 弱 SEO 页面

这类页面偏应用内部流程，目标是交互体验和状态恢复，而不是搜索收录。

建议包括：

- `/session/[id]/emotion`
- `/session/[id]/mode`
- `/session/[id]/result`
- `/session/[id]/cards`
- `/session/[id]/reflection`
- `/session/[id]/summary`
- `/history`

这些页面也应有基础 `metadata`，但不作为核心 SEO 增长页。

---

## 3. Next.js 渲染策略建议

## 3.1 首页与品牌页

建议：
- 优先 `Server Component`
- 可用静态生成或 ISR
- 核心文案直接服务端输出

原因：
- 首屏快
- 搜索引擎更稳定抓取
- 更利于 metadata 与结构化数据输出

## 3.2 分享页

建议：
- 服务端取数
- 动态 `generateMetadata`
- 根据会话内容生成专属标题与描述
- 预留 OG 图片生成能力

## 3.3 工具流程页

建议：
- 页面主体可客户端交互
- 首屏外层布局和基础 metadata 仍保留
- 核心交互与状态恢复优先

---

## 4. metadata 实施规范

## 4.1 全站基础 metadata

建议在根布局中统一配置：

- `metadataBase`
- 默认站点名
- 默认 `title template`
- 默认 `description`
- 默认 Open Graph
- 默认 Twitter Card
- 默认图标

### 建议字段

- `title`
- `description`
- `applicationName`
- `keywords`
- `authors`
- `creator`
- `publisher`
- `robots`
- `alternates.canonical`
- `openGraph`
- `twitter`
- `icons`

---

## 4.2 页面级 metadata 规范

每个重要页面建议维护：

### 必填项
- `title`
- `description`
- `canonical`

### 推荐项
- `keywords`
- `openGraph.title`
- `openGraph.description`
- `openGraph.images`
- `twitter.card`
- `twitter.title`
- `twitter.description`

### 控制项
- `robots.index`
- `robots.follow`

---

## 4.3 metadata 命名建议

### 首页
建议强调：
- 品牌词
- 核心价值词
- 工具定位词

例如方向：
- 轻量心理反思工具
- 启发、反思、行动
- 决策与情绪觉察

### 分享结果页
建议强调：
- 单次结果摘要
- 某个启发语或行动建议
- 但必须脱敏，避免暴露用户隐私

### 每日卡分享页
建议强调：
- 日期
- 卡牌主题
- 一句引导语

---

## 5. canonical 与索引策略

## 5.1 canonical 规范

所有强 SEO 页面应设置 canonical，避免重复收录。

示例类型：
- 首页 canonical 指向正式域名首页
- 分享页 canonical 指向当前分享页唯一地址
- 带筛选参数的列表页 canonical 指向主列表或规范化 URL

## 5.2 noindex 策略

以下页面建议默认不索引：

- 会话流程页 `/session/[id]/*`
- 用户私有历史页 `/history`
- 错误页 `/error`
- 风险页 `/safety/risk`

原因：
- 私密性强
- 内容临时性强
- 不适合进入搜索结果

## 5.3 index 策略

以下页面建议可索引：

- 首页 `/`
- 品牌页 / 内容页
- 匿名可公开的分享页
- 每日卡分享页

---

## 6. 分享页实施规范

## 6.1 分享页目标

分享页要同时满足：

1. 社交平台预览好看
2. 打开速度快
3. 可被搜索引擎理解
4. 不泄露用户隐私

## 6.2 推荐分享页路由

建议独立路由：

- `/share/session/[id]`
- `/share/daily-card/[date]`
- `/share/insight/[id]`

不要直接拿应用内部页面去分享，例如：
- `/session/[id]/summary`

因为内部流程页通常：
- 需要鉴权
- 文案不适合外部公开
- metadata 不稳定

## 6.3 分享页内容规范

### 会话分享页
建议公开内容：
- 一句去隐私化启发语
- 一段温和摘要
- 一个行动标签或微实验标签

不建议公开内容：
- 用户原始完整问题
- 完整反思对话
- 任何可识别个人信息

### 每日卡分享页
建议公开内容：
- 卡牌标题
- 卡牌主题
- 今日引导问题
- 日期

### 洞察分享页
建议公开内容：
- 脱敏摘要
- 风格描述
- 通用建议

---

## 6.4 Open Graph 图片规范

建议预留动态 OG 图片能力。

### OG 图应包含
- 品牌名 `照见一念`
- 页面标题
- 一句摘要文案
- 统一品牌视觉

### 不应包含
- 用户原始长文本隐私内容
- 敏感情绪细节
- 风险内容详情

### 推荐尺寸
- $1200 \times 630$

---

## 7. 结构化数据 Schema 清单

建议对强 SEO 页面补充结构化数据。

## 7.1 首页

建议 Schema：
- `WebSite`
- `Organization`
- `SoftwareApplication`

### 目的
- 让搜索引擎理解站点主体
- 强化品牌和产品属性

## 7.2 品牌介绍 / 内容页

建议 Schema：
- `WebPage`
- `Article` 或 `BlogPosting`（如果是内容页）
- `BreadcrumbList`

## 7.3 每日卡分享页

建议 Schema：
- `WebPage`
- `CreativeWork`
- `ImageObject`（如果有分享图）

## 7.4 分享结果页

建议 Schema：
- `WebPage`
- `CreativeWork`

注意：
- 避免把用户私密会话包装成公开医疗或诊断内容
- 不要误用 `MedicalWebPage`、`MedicalCondition`

## 7.5 导航层

建议 Schema：
- `BreadcrumbList`

适用页面：
- 品牌页
- 内容页
- 分享页

---

## 8. 结构化数据字段建议

## 8.1 `WebSite`

建议包含：
- 站点名称
- 站点 URL
- 语言
- 搜索入口（如后续有站内搜索）

## 8.2 `Organization`

建议包含：
- 品牌名称
- Logo
- 官方网站
- 社交链接（如后续有）

## 8.3 `SoftwareApplication`

建议包含：
- 产品名称
- 应用类别
- 操作平台（Web）
- 简短描述
- 品牌方

## 8.4 `CreativeWork`

建议包含：
- 标题
- 描述
- 日期
- 图片
- 发布者

---

## 9. 页面级 SEO 清单

## 9.1 首页 `/`

必须具备：
- 唯一标题
- 唯一描述
- 品牌与产品关键词
- `WebSite` / `Organization` / `SoftwareApplication` Schema
- canonical
- Open Graph
- Twitter Card

## 9.2 分享结果页 `/share/session/[id]`

必须具备：
- 动态标题
- 动态描述
- 动态 OG 图
- canonical
- `CreativeWork` Schema
- 隐私脱敏策略

## 9.3 每日卡分享页 `/share/daily-card/[date]`

必须具备：
- 日期型标题
- 今日卡牌描述
- OG 图
- `CreativeWork` Schema
- canonical

## 9.4 历史与流程页

建议具备：
- 基础标题
- 基础描述
- `robots: noindex`

---

## 10. `robots.txt` 规范

建议策略：

### 允许抓取
- 首页
- 品牌页
- 分享页
- 每日卡公开页

### 限制或避免索引
- `/session/`
- `/history`
- `/safety/`
- `/api/`
- 内部调试路径

说明：
- 是否完全 `Disallow` 需要结合实际产品策略
- 对部分用户态页面更建议使用 `noindex` 而不是粗暴屏蔽全部资源

---

## 11. `sitemap` 规范

建议纳入：
- 首页
- 品牌页
- 静态内容页
- 每日卡公开页
- 公开分享页

不建议纳入：
- 私有流程页
- 错误页
- 风险页
- 需要鉴权的页面

### 更新策略

建议：
- 静态路由固定生成
- 每日卡和公开分享页可动态补充

---

## 12. 内容与文案 SEO 原则

## 12.1 首页文案原则

首页要让搜索引擎和用户都快速理解：
- 这是什么产品
- 它帮助解决什么问题
- 它和普通问答工具有什么不同

## 12.2 分享页文案原则

分享页文案要：
- 简洁
- 温和
- 可传播
- 避免敏感与隐私内容

## 12.3 避免的问题

避免：
- 堆砌关键词
- 标题与正文不一致
- 完全依赖图片承载核心文案
- 核心内容只在客户端加载后才出现

---

## 13. 性能与 SEO 的关系

SEO 不只是 metadata，还包括性能。

## 13.1 必须关注的指标

- LCP
- INP
- CLS
- TTFB

## 13.2 工程建议

- 优先减少首屏 JS
- 图片按需加载
- 字体策略优化
- 核心内容尽量服务端输出
- 避免分享页依赖大型客户端状态

---

## 14. SEO 上线验收清单

上线前至少检查：

### metadata
- 每个强 SEO 页面是否有唯一 `title`
- 是否有唯一 `description`
- canonical 是否正确
- Open Graph 是否完整
- Twitter Card 是否完整

### 分享预览
- 分享结果页是否生成正确标题
- 是否显示正确摘要
- OG 图是否可访问
- 是否没有隐私泄露

### 结构化数据
- JSON-LD 是否输出
- Schema 类型是否合理
- 没有误用医疗类 Schema

### 索引控制
- 会话流程页是否 `noindex`
- 分享页是否可索引
- `robots.txt` 是否生效
- `sitemap` 是否可访问

### 性能
- 首页 Lighthouse 基本通过
- 分享页首屏快
- 核心文案无需等待客户端请求

---

## 15. 推荐实施顺序

## 第一步：先搭基础 metadata

优先完成：
- 根布局默认 metadata
- 首页 metadata
- `robots.txt`
- `sitemap`

## 第二步：做分享页骨架

优先完成：
- `/share/session/[id]`
- `/share/daily-card/[date]`
- 动态 metadata

## 第三步：补 JSON-LD

优先补：
- 首页 `WebSite`
- 首页 `Organization`
- 首页 `SoftwareApplication`
- 分享页 `CreativeWork`

## 第四步：补 OG 图片

优先为：
- 分享结果页
- 每日卡分享页

## 第五步：做上线巡检

上线前统一验证：
- metadata
- robots
- sitemap
- JSON-LD
- 分享预览
- 性能

---

## 16. 最终建议

如果把这份文档压缩成一句话：

> 先把首页和分享页做成真正可被搜索与分享理解的页面，再把流程页做好基础 metadata 与 noindex 控制，同时通过 JSON-LD、OG 图、canonical、robots 和 sitemap 建立完整的 SEO 工程能力。

对这个项目当前阶段，SEO 最应该优先做的 5 件事是：

1. 首页完整 metadata
2. 分享结果页独立路由
3. 每日卡分享页独立路由
4. `robots.txt` 与 `sitemap`
5. 首页与分享页 JSON-LD
