import hashlib, json, os, time
from datetime import datetime, timezone
import feedparser
import requests
import random
import re

WEB3_SOURCES = [
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

FEEDS_FILE = "feeds.txt"
STATE_FILE = "state.json"
OUT_DIR = "digests"

def load_feeds():
    feeds = []
    # hardcoded web3 sources
    for name, url in WEB3_SOURCES:
        feeds.append((name, url))
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # support format: Title:URL or Title：URL
            if ":" in line or "：" in line:
                parts = line.split("：") if "：" in line else line.split(":")
                line = parts[-1].strip()
            # support format: Title:URL or Title：URL
            if ':' in line or '：' in line:
                parts = line.split('：') if '：' in line else line.split(':')
                line = parts[-1].strip()
            feeds.append((None, line))
    return feeds

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"seen": [], "fail_counts": {}}  # 存 hash 列表，够用
    except Exception:
        return {"seen": [], "fail_counts": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def parse_time_ts(value):
    if not value:
        return 0
    try:
        from dateutil import parser as dp
        dt = dp.parse(value)
        return int(dt.timestamp())
    except Exception:
        return 0

def stable_id(entry):
    base = (getattr(entry, "id", "") or getattr(entry, "link", "") or getattr(entry, "title", "")).strip()
    if not base:
        base = json.dumps(entry, default=str, ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def fetch_new_items(feeds, state, max_items=200):
    seen = set(state.get("seen", []))
    fail_counts = state.get("fail_counts", {})
    new_items = []

    for name, url in feeds:
        source_name = name or url
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code in (403, 406):
                print(f"WAF Blocked: {source_name} ({resp.status_code})")
                fail_counts[source_name] = fail_counts.get(source_name, 0)
                continue
            if resp.status_code == 404:
                fail_counts[source_name] = fail_counts.get(source_name, 0) + 1
                if fail_counts[source_name] >= 3:
                    print(f"SOURCE INVALID ALERT: {source_name} (404 x3)")
                continue
            resp.raise_for_status()
            d = feedparser.parse(resp.content)
        except requests.exceptions.RequestException:
            fail_counts[source_name] = fail_counts.get(source_name, 0) + 1
            print(f"FETCH ERROR: {source_name}")
            continue
        except Exception:
            print(f"PARSE ERROR: {source_name}")
            continue

        # jitter between requests
        time.sleep(random.uniform(1, 3))

        entries = d.entries if hasattr(d, "entries") else []
        if getattr(d, "bozo", False) and not entries:
            # fallback parse title/link from raw xml
            titles = re.findall(rb"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", resp.content, re.I)
            links = re.findall(rb"<link>(.*?)</link>", resp.content, re.I)
            for t, t2 in titles[:50]:
                title = (t or t2).decode("utf-8", "ignore")
                link = links.pop(0).decode("utf-8", "ignore") if links else ""
                if title and link:
                    entries.append({"title": title, "link": link})

        for e in entries[:200]:
            sid = stable_id(e)
            if sid in seen:
                continue
            seen.add(sid)

            title = getattr(e, "title", "") or e.get("title", "")
            link = getattr(e, "link", "") or e.get("link", "")
            summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            if len(summary) > 200:
                summary = summary[:200]

            pub = getattr(e, "published", "") or getattr(e, "updated", "") or getattr(e, "pubDate", "")
            ts = parse_time_ts(pub)

            item = {
                "source_name": source_name,
                "title": re.sub(r"<[^>]+>", "", title),
                "url": link,
                "summary": re.sub(r"<[^>]+>", "", summary),
                "publish_time_ts": ts,
                "guid": sid,
            }
            if item["title"] and item["url"]:
                new_items.append(item)
            if len(new_items) >= max_items:
                break

    state["seen"] = list(seen)[-5000:]
    state["fail_counts"] = fail_counts
    new_items.sort(key=lambda x: x.get("publish_time_ts", 0), reverse=True)
    return new_items

def build_material_pack(items):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_at_utc": now,
        "window_hours": 4,  # 你的扫描周期
        "items": items,
        # 你可以在这里加：关键词过滤、按来源权重打分、分类标签等
    }

def post_to_writer_api(material_pack):
    url = os.getenv("WRITER_API_URL")
    if not url:
        return False, "WRITER_API_URL missing"

    headers = {"Content-Type": "application/json"}
    key = os.getenv("WRITER_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    resp = requests.post(url, headers=headers, json=material_pack, timeout=60)
    return resp.ok, f"{resp.status_code} {resp.text[:200]}"

def save_digest(material_pack):
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    path = f"{OUT_DIR}/digest-{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(material_pack, f, ensure_ascii=False, indent=2)
    return path

def main():
    feeds = load_feeds()
    state = load_state()

    new_items = fetch_new_items(feeds, state)
    pack = build_material_pack(new_items)

    out_path = save_digest(pack)
    ok, msg = post_to_writer_api(pack)

    
    # write site data.json for static site
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": pack["run_at_utc"], "items": pack["items"]}, f, ensure_ascii=False, indent=2)

    save_state(state)
    print("new_items:", len(new_items))
    print("saved:", out_path)
    print("posted:", ok, msg)

if __name__ == "__main__":
    main()
