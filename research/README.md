# Web3 research pipeline

二阶段研究流水线：RSS 增量发现 + r.jina.ai 全文抽取。

---

## 目标

相比 `run.py` 的轻量 digest，`research/run.py` 提供更适合写作和分析的完整素材：
- 原文链接
- 发布时间戳
- 全文 markdown
- 标签与抓取状态

---

## 流程说明

1. 从内置 RSS 源抓取最近 `WINDOW_HOURS`（默认 8h）内容
2. 过滤无效条目，清洗标题
3. 按 URL 计算 `uuid` 并与 `research/state.json` 去重
4. 调用 `https://r.jina.ai/<url>` 抽取全文
5. 保存为 `research/output/research-YYYYMMDD-HHMM.json`
6. （可选）写入飞书多维表

---

## 输出文件结构

```json
[
  {
    "uuid": "sha256(url)",
    "source": "PANews",
    "title": "...",
    "original_url": "...",
    "publish_ts": 1772...,
    "content_markdown": "...",
    "tags": ["..."],
    "status": "success|partial_content"
  }
]
```

### 字段解释
- `uuid`：去重主键（基于 URL）
- `status`：
  - `success`：正文抽取成功
  - `partial_content`：正文抽取失败，已降级内容

---

## 运行配置

### 固定参数（代码内）
- `WINDOW_HOURS = 8`
- `MAX_ITEMS_PER_RUN = 40`

### 环境变量（飞书写入）
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- `FEISHU_TABLE_ID`

> 当前实现里，飞书变量缺失会抛 `FEISHU_MISSING`。如果你的目标只是落地 JSON，请在本地改为“缺失变量则跳过飞书写入”。

---

## 常见失败点

1. **RSS fetch error**
- 原因：源站波动、超时、WAF
- 处理：重跑 + 增加重试/退避

2. **r.jina.ai 抽取失败**
- 原因：目标站限制、临时网络问题
- 处理：自动降级 `partial_content`，后续可补抓

3. **飞书写入失败**
- 原因：token/表配置错误、权限不足
- 处理：先验证 app 凭据，再检查 table schema

---

## 给下游（内容工厂）的使用建议

- 优先消费 `research/output`（信息更完整）
- 打包前做二次去重：`original_url`
- 分组前过滤无效项：`title + original_url + content_markdown`
- 严格按 `publish_ts` 倒序
- 产出包时保留最小字段：`id/source/title/url/summary(publish_ts)`

---

## 下一步可优化

- 增加 source 级抓取成功率统计
- 增加重试与指数退避
- 抽取失败 URL 队列化重跑
- 把“可选飞书写入”改成真正非阻断
