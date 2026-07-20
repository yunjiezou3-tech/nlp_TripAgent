# 分组地点选择与住宿推荐设计

## 目标

在旅行规划工作流的 `chat -> information -> recommend -> strategy -> route` 主链中，让用户能够表达住宿偏好，并在同一选择界面中确认景点、饭店和住宿。选中的三类地点将作为行程生成的强约束；酒店还将作为每日路线的住宿锚点，并成为后续酒店预订草稿的默认目标。

## Google Places 数据能力

项目现有服务使用 `googlemaps` Python client 调用 Places API Legacy，因此本期继续使用该 client：

- 景点使用 `tourist_attraction`。
- 饭店使用 `restaurant`。
- 酒店使用 `lodging`，不再使用当前的 `hotel` 查询类型。
- 候选结果使用 Place Details 补全名称、地址、坐标、评分、价格档、照片、营业状态、网站和简介。

Google Places 适用于发现和推荐住宿，不提供实时房态、房价或可预订房型。新版 Places API 也支持 Nearby Search 和 Text Search，但本期不迁移现有 Python client；新版迁移作为独立后续工作。

参考：

- https://developers.google.com/maps/documentation/places/web-service/legacy/supported_types
- https://developers.google.com/maps/documentation/places/web-service/nearby-search
- https://developers.google.com/maps/documentation/places/web-service/place-types

## 用户输入与候选生成

`ChatAgent` 将把自然语言中的住宿偏好写入 `user_info.accommodation_preferences`：

```json
{
  "area": "新宿站附近",
  "price_level": {"min": 2, "max": 3},
  "min_rating": 4.2,
  "max_distance_to_core_km": 3,
  "amenities": ["早餐", "亲子", "洗衣机", "健身房", "吧台"]
}
```

`information` 阶段以目的地中心坐标为基础，分别生成 `attractions`、`restaurants` 和 `hotels`。

- 区域、价格档、最低评分和距核心景点距离是确定性过滤条件。
- 早餐、亲子、无障碍、洗衣机、健身房、吧台等是 LLM 重排权重。每个酒店候选包含 `match_score` 和 `match_reasons`，用于解释推荐依据。
- 三类候选统一包含 `id`、`kind`、`name`、`address`、`location`、`rating`、`price_level`、`photos`、`summary`、`types` 和 `source`。酒店额外包含 `match_score` 与 `match_reasons`。

## 分组选择与工作流状态

推荐页采用已确认的分组选择交互：景点、饭店和住宿独立浏览、同一次确认。

- 景点至少选择一项。
- 饭店可多选，也可跳过；未选择的餐段由规划 agent 按位置和偏好补充。
- 住宿最多选择一项，也可跳过；未选择时规划 agent 可以给出建议，但不将任意酒店视为用户确认的住宿。

新增 workflow state：

```json
{
  "accommodation_preferences": {},
  "restaurants": [],
  "hotels": [],
  "selected_attractions": [],
  "selected_restaurants": [],
  "selected_hotel": null
}
```

`/api/process` 与 `/api/stream` 返回三类候选；前端确认时提交 `selected_attraction_ids`、`selected_restaurant_ids` 和 `selected_hotel_id`。后端按 ID 校验并保存三组选择，拒绝不属于当前候选集的 ID。

## 行程、路线与预订草稿

`strategy` 将选中的景点和饭店作为必须纳入的地点，按每日时段安排。酒店不会作为游玩活动显示，但会作为每日路线的起终点：

- 选中酒店时，路线从酒店出发并回到酒店；route agent 使用其坐标优化景点和饭店的顺序。
- 未选酒店时，沿用当前景点间路线优化逻辑。
- 选中饭店带入每日计划，未选餐段由 strategy agent 根据景点位置和餐饮偏好补齐。
- 后续 `booking` 流程优先使用 `selected_hotel` 生成酒店草稿；仅在用户未选酒店时，才使用推荐排序第一项作为候选。

## 容错与测试

Google Places 请求采用 fail-soft：一类检索失败时，该类别返回空数组和可展示的错误原因，其余类别仍可选择并继续；三类结果均为空时才阻止进入选择环节。不会返回伪装为真实地点的 Sample Hotel 或 Sample Restaurant。

测试将覆盖：

1. 住宿偏好从中文自然语言解析为结构化字段。
2. 酒店检索使用 `lodging`，并应用价格档、评分和距离过滤。
3. 设施偏好进入 LLM 重排输入和推荐理由。
4. 三类选中 ID 被校验并写入 session state。
5. 已选饭店进入 strategy 计划，已选酒店成为 route 的起终点。
6. 单类 Google Places 失败不阻断其他类别选择；全量失败返回可恢复错误。
