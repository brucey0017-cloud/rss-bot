import hashlib, json, os, time, random, re
from datetime import datetime, timezone
import feedparser
import requests
from dateutil import parser as dp

SOURCES = [
    ("BlockBeats", "https://api.theblockbeats.news/v2/rss/article"),
    ("Odaily", "https://rss.odaily.news/rss/post"),
    ("PANews", "https://www.panewslab.com/zh/rss/foryou.xml"),
    ("ChainCatcher", "https://www.chaincatcher.com/rss/clist"),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/121.0.0.0 Safari/537.36",
]

STATE_FILE = "research/state.json"
WINDOW_HOURS = 4
MAX_ITEMS_PER_RUN = 40
OUT_DIR = "research/output"


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def stable_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def parse_time_ts(value):
    if not value:
        return 0
    try:
        dt = dp.parse(value)
        return int(dt.timestamp())
    except Exception:
        return 0


def normalize_text(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def fetch_rss_items():
    items = []
    now_ts = int(datetime.now(timezone.utc).timestamp())
    min_ts = now_ts - WINDOW_HOURS * 3600
    for name, url in SOURCES:
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code in (403, 406):
                print(f"WAF Blocked: {name} ({resp.status_code})")
                continue
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception:
            print(f"RSS fetch error: {name}")
            continue

        for e in feed.entries[:50]:
            link = getattr(e, "link", "") or e.get("link", "")
            title = getattr(e, "title", "") or e.get("title", "")
            pub = getattr(e, "published", "") or getattr(e, "updated", "")
            tags = [t.get("term") for t in getattr(e, "tags", []) if isinstance(t, dict) and t.get("term")]
            if link:
                if parse_time_ts(pub) and parse_time_ts(pub) < min_ts:
                    continue
                items.append({
                    "source": name,
                    "title": normalize_text(title),
                    "original_url": link,
                    "publish_ts": parse_time_ts(pub),
                    "tags": tags,
                })

        time.sleep(random.uniform(1, 3))

    return items


def extract_full_text(url):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "X-Return-Format": "markdown",
        "X-Target-Selector": "body",
    }
    extract_url = f"https://r.jina.ai/{url}"
    resp = requests.get(extract_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text




def feishu_get_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"feishu token error: {data}")
    return data["tenant_access_token"]


def feishu_write_records(token, app_token, table_id, records):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"records": records}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"feishu write error: {data}")
    return data


def main():
    state = load_state()
    seen = set(state.get("seen", []))

    rss_items = fetch_rss_items()
    results = []

    for item in rss_items[:MAX_ITEMS_PER_RUN]:
        uid = stable_id(item["original_url"])
        if uid in seen:
            continue
        seen.add(uid)

        content = ""
        status = "success"
        try:
            content = extract_full_text(item["original_url"])
        except Exception:
            # fallback to RSS summary
            status = "partial_content"
            content = item.get("summary") or ""

        results.append({
            "uuid": uid,
            "source": item["source"],
            "title": item["title"],
            "original_url": item["original_url"],
            "publish_ts": item["publish_ts"],
            "content_markdown": content,
            "tags": item.get("tags", []),
            "status": status,
        })

        time.sleep(random.uniform(5, 10))

    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    out_path = f"{OUT_DIR}/research-{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    state["seen"] = list(seen)[-5000:]
    save_state(state)
    print("items:", len(results))
    print("saved:", out_path)


    # optional: write to Feishu Bitable
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    app_token = os.getenv("FEISHU_APP_TOKEN")
    table_id = os.getenv("FEISHU_TABLE_ID")
    if app_id and app_secret and app_token and table_id and results:
        try:
            token = feishu_get_token(app_id, app_secret)
            batch = []
            for r in results:
                batch.append({"fields": {
                    "uuid": r["uuid"],
                    "source": r["source"],
                    "title": r["title"],
                    "original_url": r["original_url"],
                    "publish_ts": r["publish_ts"],
                    "content_markdown": r["content_markdown"],
                    "status": r["status"],
                    "tags": ",".join(r.get("tags", [])),
                }})
                if len(batch) == 100:
                    feishu_write_records(token, app_token, table_id, batch)
                    batch = []
            if batch:
                feishu_write_records(token, app_token, table_id, batch)
            print("feishu: ok")
        except Exception as e:
            print("feishu error:", e)


if __name__ == "__main__":
    main()
