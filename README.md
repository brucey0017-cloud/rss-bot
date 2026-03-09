# rss-bot

RSS 自动剪报 + 深度抽取流水线（Web3 场景）。

> 当前仓库包含两条独立但互补的流程：
> 1) `run.py`：生成 digest（轻量剪报）
> 2) `research/run.py`：抓取全文（r.jina.ai）并输出 research 结果（可选写入飞书多维表）

---

## 目录结构

```text
.
├─ feeds.txt                      # 扩展 RSS 源列表
├─ run.py                         # digest 主流程
├─ state.json                     # digest 去重状态
├─ digests/                       # digest 输出（每次运行一个文件）
├─ docs/                          # 静态预览页面（index/app/style + data.json）
├─ research/
│  ├─ run.py                      # research 主流程（全文抽取）
│  ├─ state.json                  # research 去重状态
│  ├─ output/                     # research 输出
│  └─ README.md                   # research 详细说明
└─ .github/workflows/
   ├─ digest.yml                  # 每4小时17分触发 digest
   └─ research.yml                # 每4小时37分触发 research
```

---

## 两条流水线在做什么

### A) Digest 流水线（`run.py`）

- 数据源：
  - 内置 4 个 Web3 媒体源（BlockBeats / Odaily / PANews / ChainCatcher）
  - `feeds.txt` 中的额外 RSS/Atom 源
- 处理步骤：
  1. 抓取 feed
  2. 解析条目
  3. 生成稳定 ID（`sha256(id|link|title)`）
  4. 根据 `state.json` 去重
  5. 产出 `digests/digest-YYYYMMDD-HHMM.json`
  6. 同步写 `docs/data.json`（静态页面展示）
  7. 可选 POST 到 `WRITER_API_URL`

输出示例字段：

```json
{
  "run_at_utc": "...",
  "window_hours": 4,
  "items": [
    {
      "source_name": "PANews",
      "title": "...",
      "url": "...",
      "summary": "...",
      "publish_time_ts": 1772...,
      "guid": "sha256..."
    }
  ]
}
```

### B) Research 流水线（`research/run.py`）

- 数据源：内置 4 个 Web3 媒体源（同上）
- 时间窗口：默认最近 `WINDOW_HOURS=8` 小时
- 处理步骤：
  1. 抓取 RSS
  2. 过滤（含 ChainCatcher 快讯过滤）
  3. 按 URL 生成 `uuid` 去重（`research/state.json`）
  4. 用 `https://r.jina.ai/<url>` 抽取全文 markdown
  5. 输出 `research/output/research-YYYYMMDD-HHMM.json`
  6. 可选写入飞书多维表（批量写入）

输出示例字段：

```json
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
```

---

## GitHub Actions 调度

- `digest.yml`：`17 */4 * * *`（UTC）
- `research.yml`：`37 */4 * * *`（UTC）

两个 workflow 都会自动提交产物到仓库（`git add ... && git push`）。

---


## 与 content-factory 的自动联动（防静默失败）

`research.yml` 在研究任务结束后会自动触发 `content-factory` 打包（`repository_dispatch`）。

已启用 **强制校验**：
- 触发接口必须返回 **HTTP 204** 才算成功
- 非 204（如 401/403/404）会让 workflow **直接失败（红灯）**
- 失败时会打印响应体，便于快速定位权限/配置问题

这样可以避免“看起来 research 成功、但下游没收到触发”的静默故障。

### 必要 Secret
- `CONTENT_FACTORY_DISPATCH_TOKEN`

建议权限：
- 对 `content-factory` 仓库具备可触发 dispatch 的权限（常见做法：classic PAT 带 `repo`）

## 环境变量

### Digest 可选
- `WRITER_API_URL`：下游写作 API 地址
- `WRITER_API_KEY`：下游 API 鉴权（可选）

### Research（飞书写入）
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- `FEISHU_TABLE_ID`

> 注意：当前 `research/run.py` 中，如果飞书变量缺失会触发 `FEISHU_MISSING` 异常。若只想本地落地 JSON、不中断流程，需在代码中改为「缺失变量则跳过写飞书」。

---

## 本地运行

```bash
# digest
python -m pip install feedparser requests python-dateutil
python run.py

# research
python -m pip install feedparser requests python-dateutil
python research/run.py
```

---

## 去重与口径说明（给下游消费方）

- 本仓库“是否已抓取过”由 `state.json` / `research/state.json` 控制（基于 hash）。
- 如果下游要做素材包，建议二次去重：
  - 主键：`url` 或 `original_url`
  - 保留最新 `publish_ts`
  - 严格按时间倒序打包
  - 过滤无效项（title/url/content 为空）

---

## 常见问题

1) **为什么最新 digest 只有几十条？**  
因为 digest 是“增量窗口 + 去重”结果，不是全量库存。

2) **为什么有些全文缺失？**  
`r.jina.ai` 抽取失败时会降级为 `partial_content`。

3) **为什么看起来没更新？**  
先检查 workflow 是否成功、`research/output` 新文件是否生成、`state.json` 是否过度去重。

---

## 维护建议

- 增加字段字典文档（data contract）
- 增加“抓取成功率 / 抽取成功率”统计输出
- 把飞书写入改为真正 optional（不阻断本地产物）
- 为 `feeds.txt` 增加源健康检查（404 连续失败告警）
