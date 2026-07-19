# Chat 信息摘要、增量推荐与候选价格设计

## 目标

本轮在现有 `chat -> information -> recommend -> strategy -> route` 链路上完成三项改造：

1. Chat 反问固定输出“已收集到的信息 + 针对缺失信息的提问”，并覆盖必填字段和已提供的可选偏好。
2. 用户在候选阶段可通过自然语言要求增加景点、餐厅或住宿；新结果追加到已有列表，保留已选项且不重复。
3. 餐厅与住宿候选展示图片和价格信息；制定计划前必须确定具体日期，酒店房型价格按入住日期由 `CtripMockProvider` 提供。

本轮不接入真实携程，不把 Google `price_level` 或 mock 酒店报价描述为实时真实价格，也不重做完整 provider 架构。

## 已确认决策

- “更多推荐”采用追加模式：只增加未展示过的新候选，不替换旧列表，不清除已选项。
- “更多博物馆”“更多便宜餐厅”等附加条件只影响本轮增量检索，不写入长期用户偏好。
- 餐厅优先展示 Google `priceRange`；缺失时根据 `price_level` 生成“参考人均 ¥X-Y（估算）”，同时显示经济、中等或较高。
- 酒店基础资料和图片来自 Google Places；指定日期的房型、每晚价、总价、早餐、取消政策和模拟库存来自 `CtripMockProvider`。
- `start_date = not decided` 不再满足信息完整条件。进入 Information 和酒店报价前必须有有效的具体日期。

## 组件边界

### TravelGraph

`TravelGraph` 仅负责编排：接收 step、调用服务、合并状态、决定下一步。它不直接解析“更多推荐”，也不直接构造价格或图片字段。

### ChatAgent 与 CollectedInfoFormatter

`ChatAgent` 继续负责结构化抽取和针对缺失字段生成自然语言问题。新增确定性的 `CollectedInfoFormatter`，按固定顺序将当前状态格式化为一行一个字段的摘要。

最终响应由两部分拼接：

```text
已收集到的信息
称呼：周宁
出发地：北京
目的地：东京
旅行天数：5 天
出行人数：2 人
健康状况：良好
兴趣偏好：艺术馆、当地美食
住宿偏好：地铁附近、含早餐
特殊要求：无障碍优先

还需要补充
请告诉我具体出发日期和预算范围。
```

规则：

- 已收集区包含所有已有必填字段和可选偏好；没有值的字段不显示为空行。
- 字段标题、顺序和换行由代码控制，LLM 只能生成“还需要补充”后的问题。
- 问题只能涉及 `missing_fields`，不得规划景点、餐厅、酒店、路线或行程。
- API 同时保留结构化 `collected_info` 和 `missing_fields`，避免前端只能解析文本。

### DateResolver

新增轻量日期解析与校验边界：

- 每次 Chat 请求将服务器当前日期以 `current_date: YYYY-MM-DD` 注入抽取上下文。
- 支持把“下周五”“今年国庆”等相对日期解析为具体 `start_date`。
- `start_date` 必须符合 `YYYY-MM-DD`，且不得早于 `current_date`。
- `end_date`/退房日由 `start_date + days` 计算。
- 日期无效或未定时停留在 Chat，不调用 Information、天气、酒店报价或策略规划。

### InformationRefinementService

该服务接收候选阶段的自然语言输入并输出结构化意图：

```json
{
  "intent": "more_candidates",
  "categories": ["restaurant"],
  "transient_filters": {
    "keyword": "便宜",
    "max_price_level": 1
  }
}
```

候选阶段支持三类意图：

- `more_candidates`：按类别进行增量检索。
- `update_preferences`：回到 Chat 修改长期偏好，清除由旧偏好派生的候选与计划。
- `confirm_selection`：进入现有策略和路线生成。

若用户只说“再推荐一些”而未指出类别，返回澄清问题，不发起外部检索。规则匹配优先识别“景点/餐厅/酒店/住宿”等明确词，LLM 只用于补充同义表达和临时条件。

### PlaceCandidateEnricher

该服务将 Google 和 mock 数据标准化为统一候选结构，并负责价格来源与估算标识。它不负责排序和 workflow 跳转。

Google Places 的搜索与基础详情沿用现有实现。对实际展示批次进行最佳努力增强：

- 图片优先使用 Places 返回的 photo reference，并保留 attribution 信息。
- 餐厅价格优先请求 Places API New 的 `priceRange`；该字段缺失或请求失败时回退到 `price_level`。
- `priceRange` 是地点价格区间，不强制描述为人均；前端显示“Google 价格区间”。
- fallback 显示“参考人均 ¥X-Y（估算）”，不得去掉估算标记。

估算映射：

| price_level | 档位 | 参考人均 |
|---|---|---|
| 0-1 | 经济 | ¥30-80 |
| 2 | 中等 | ¥80-180 |
| 3 | 较高 | ¥180-350 |
| 4 | 较高 | ¥350 起 |

4 级估算使用 `min=350, max=null`，前端显示“参考人均 ¥350 起（估算）”。

Google `priceRange` 属于 Places API New 的付费字段，只有可见批次才做增强，避免一次性为全部原始结果调用高成本详情接口。

## 候选数据契约

景点、餐厅和酒店继续共享现有基础字段，并增加：

```json
{
  "photos": [
    {
      "url": "...",
      "width": 800,
      "height": 600,
      "attribution": "..."
    }
  ],
  "price": {
    "source": "google_price_range | estimated_price_level | ctrip_mock",
    "min": 80,
    "max": 180,
    "currency": "CNY",
    "unit": "person | room_night | stay",
    "level_label": "中等",
    "is_estimate": true,
    "as_of": "2026-07-20"
  }
}
```

酒店另外增加：

```json
{
  "stay": {
    "check_in": "2026-10-01",
    "check_out": "2026-10-06",
    "nights": 5
  },
  "room_offers": [
    {
      "id": "...",
      "room_type": "高级大床房",
      "nightly_rate": 688,
      "total_amount": 3440,
      "currency": "CNY",
      "breakfast": "双早",
      "cancellation_policy": "入住前一天 18:00 前可免费取消",
      "inventory_status": "模拟有房",
      "source": "ctrip_mock",
      "is_mock": true
    }
  ]
}
```

没有 mock 报价时仍展示 Google 酒店基础资料，并显示“暂无日期报价”，不制造 fallback 房价。

## Session 状态

新增正式字段：

```json
{
  "current_date": "2026-07-20",
  "trip_date_status": "missing | valid | invalid",
  "information_refinement": {},
  "candidate_price_context": {
    "check_in": "2026-10-01",
    "check_out": "2026-10-06",
    "guests": 2
  },
  "candidate_search_state": {
    "attraction": {
      "seen_ids": [],
      "next_page_token": null,
      "radius_m": 10000,
      "batch_no": 1,
      "exhausted": false
    },
    "restaurant": {},
    "hotel": {}
  }
}
```

`seen_ids` 在 JSON 中使用数组持久化。临时筛选条件在单次调用结束后清空，不能合并进 `user_info`。

## 增量检索与合并

初次 Information 完成后，候选页提供轻量自然语言输入框。示例：

- “再推荐一些景点”
- “多来几家便宜餐厅”
- “再找几家带早餐的酒店”

增量检索顺序：

1. 解析目标类别与本轮临时条件。
2. 优先消费 Google 的 `next_page_token`。
3. 排除 `seen_ids` 和当前候选 ID。
4. 若无新结果且没有可用 page token，将搜索半径扩大一次。
5. 对新批次做排序、图片与价格增强。
6. 返回 `candidate_delta`，不返回替换后的全量列表。
7. 前端按 ID 追加并保持当前已选对象。

连续扩大范围仍无新结果时，将该类别标记为 `exhausted`，并返回“该区域暂无更多匹配结果”。用户改变临时条件后可继续发起新一轮检索，但仍不得重复已展示 ID。

## API 与前端

`/api/process` 和 `/api/stream` 增加：

- `collected_info`
- `current_date`
- `trip_date_status`
- `candidate_delta`
- `candidate_search_state`
- `information_message`

候选页新增自然语言输入框，使用当前 session 和 `recommend` step。服务端意图识别后返回增量数据。前端 store 以 ID 合并 `candidate_delta`，不得覆盖已有候选或已选项。

餐厅和酒店卡片增加：

- 首张图片与缺图占位图。
- Google 价格区间或带估算标识的参考人均。
- 经济、中等、较高标签。
- 酒店入住/退房日期、首选房型、每晚价、总价、早餐和取消政策。
- `携程模拟报价` 或 `暂无日期报价` 来源标识。

图片加载失败只替换当前图片为占位图，不移除候选。

## 错误处理

- 单一类别检索失败时，保留其他类别、旧候选和全部已选项。
- Places API New 价格增强失败时回退 `price_level`，不使候选搜索失败。
- Google 图片缺失或加载失败时使用本地占位图。
- `CtripMockProvider` 失败时酒店仍可选择，但不显示虚假价格。
- 意图类别不明确时只追问类别，不调用 Google。
- 分页 token 暂不可用时允许有限重试；失败后扩大一次半径，不无限重试。
- 日期缺失、无效或早于当前日期时保持 `chat` step，并返回明确的日期问题。

## 测试与验收

### Chat 与日期

- 已收集信息按固定顺序一行一项，包含已有必填和可选偏好。
- LLM 输出不能改变摘要结构，也不能询问 `missing_fields` 之外的内容。
- `not decided`、过去日期和无效日期不能进入 Information。
- 相对日期结合 `current_date` 解析为明确日期。

### 增量推荐

- “更多餐厅”只追加餐厅且不重复。
- “更多便宜餐厅”的便宜条件只影响本轮，不改写用户预算。
- 已选景点、餐厅和酒店在追加后保持不变。
- 类别不明确时不调用外部检索。
- page token 用尽后扩大半径；仍无结果时正确标记 exhausted。

### 图片与价格

- 餐厅和酒店候选有图片或本地占位图。
- Google `priceRange` 优先于 `price_level` 估算。
- fallback 同时展示人均区间、档位和估算标识。
- 酒店 mock 房型使用正确入住日期、夜数、每晚价和总价。
- mock 报价失败时不生成伪造房价。

### 回归

- 初次 `chat -> information -> recommend` 流程保持可用。
- 地点确认后 `strategy -> route -> complete` 保持可用。
- 酒店与机票预订草稿继续使用同一 session，且优先复用用户选中的酒店。
- 任一类别增强失败不会破坏其他类别或原有候选。

## Google 能力边界

- Places API 可提供地点图片、`priceLevel` 和可能存在的 `priceRange`。
- Places API 不提供面向普通消费者的指定日期酒店房型库存与实时房价。
- Google Hotel Prices 面向 Hotel Center/酒店数据合作伙伴，不作为本项目消费者酒店搜索接口。
- 因此本轮酒店日期报价继续使用 `CtripMockProvider`，未来真实接携程时替换 provider，不修改候选和前端契约。
