import hashlib, json, os, time
from datetime import datetime, timezone
import feedparser
import requests

FEEDS_FILE = "feeds.txt"
STATE_FILE = "state.json"
OUT_DIR = "digests"

def load_feeds():
    feeds = []
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            feeds.append(line)
    return feeds

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"seen": []}  # 存 hash 列表，够用
    except Exception:
        return {"seen": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def stable_id(entry):
    base = (getattr(entry, "id", "") or getattr(entry, "link", "") or getattr(entry, "title", "")).strip()
    if not base:
        base = json.dumps(entry, default=str, ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def fetch_new_items(feeds, state, max_items=200):
    seen = set(state.get("seen", []))
    new_items = []

    for url in feeds:
        d = feedparser.parse(url)
        for e in d.entries[:200]:
            sid = stable_id(e)
            if sid in seen:
                continue
            seen.add(sid)

            item = {
                "title": getattr(e, "title", ""),
                "link": getattr(e, "link", ""),
                "source": getattr(d.feed, "title", "") or url,
                "published": getattr(e, "published", "") or getattr(e, "updated", ""),
            }
            # 过滤掉明显无效
            if item["title"] and item["link"]:
                new_items.append(item)

            if len(new_items) >= max_items:
                break

    state["seen"] = list(seen)[-5000:]  # 控制体积
    return new_items

def build_material_pack(items):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_at_utc": now,
        "window_hours": 6,  # 你的扫描周期
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

    save_state(state)
    print("new_items:", len(new_items))
    print("saved:", out_path)
    print("posted:", ok, msg)

if __name__ == "__main__":
    main()
