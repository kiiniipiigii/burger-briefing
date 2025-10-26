import os, re, hashlib, sqlite3, time
from datetime import datetime, timedelta
import feedparser, requests, trafilatura
from dateutil import tz
from rapidfuzz import fuzz
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer

# === Settings ===
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
KST = tz.gettz(os.getenv("TZ", "Asia/Seoul"))

RSS_FEEDS = [
    # Global industry
    "https://www.qsrmagazine.com/feed/",
    "https://www.restaurantbusinessonline.com/rss.xml",
    "https://www.nrn.com/rss.xml",
    # Add KR portals/brand newsroom RSS below
]

KEYWORDS = [
    # Korean
    "버거","햄버거","신메뉴","한정","콜라보","한정판","신규 출",
    # English
    "burger","hamburger","limited","collab","collaboration","new menu","launch"
]

BRAND_HINTS = ["맥도날드","버거킹","롯데리아","맘스터치","쉐이크쉑",
               "McDonald","Burger King","Lotteria","Mom’s Touch","Shake Shack","Subway","Wendy","Five Guys","In-N-Out"]

DB = "seen.sqlite3"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS items (
        url TEXT PRIMARY KEY,
        title TEXT,
        content_hash TEXT,
        published_kst TEXT
    )""")
    conn.commit()
    return conn

def normalize_url(url:str) -> str:
    if not url: return ""
    url = re.sub(r"(\?|&)(utm_[^=]+|fbclid|gclid)=[^&]+", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url.strip()

def fetch_article(url:str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True, timeout=20)
        if not downloaded: return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_images=False)
        return text or ""
    except Exception:
        return ""

def simple_kw_match(title:str, summary:str) -> bool:
    blob = f"{title} {summary}".lower()
    return any(kw.lower() in blob for kw in KEYWORDS)

def summarize_text(text:str, sent_count:int=2) -> str:
    text = text.strip()
    if not text:
        return ""
    parser = PlaintextParser.from_string(text, Tokenizer("korean"))
    summ = TextRankSummarizer()
    sents = summ(parser.document, sent_count)
    out = " ".join([str(s) for s in sents]).strip()
    return out if len(out) > 40 else (text[:240] + ("..." if len(text) > 240 else ""))

def similar(a:str, b:str) -> int:
    return fuzz.token_set_ratio(a or "", b or "")

def build_blocks(items):
    blocks = []
    header = {"type":"header","text":{"type":"plain_text","text":f"버거 업계 데일리 브리핑 • {datetime.now(KST).strftime('%Y-%m-%d (%a)')}"}}
    blocks.append(header)
    blocks.append({"type":"divider"})
    if not items:
        blocks.append({"type":"section","text":{"type":"mrkdwn","text":"오늘 새 소식이 없습니다."}})
        return blocks
    for it in items:
        title = it["title"][:160]
        url = it["url"]
        summ = it.get("summary","")
        brand_tag = ""
        for b in BRAND_HINTS:
            if b.lower() in (title + " " + summ).lower():
                brand_tag = f" • {b}"
                break
        text = f"*<{url}|{title}>*{brand_tag}\n{summ}"
        blocks.append({"type":"section","text":{"type":"mrkdwn","text":text}})
        blocks.append({"type":"divider"})
    return blocks

def post_to_slack(blocks):
    if not SLACK_WEBHOOK:
        raise RuntimeError("SLACK_WEBHOOK env not set")
    payload = {"blocks": blocks}
    r = requests.post(SLACK_WEBHOOK, json=payload, timeout=20)
    r.raise_for_status()

def main():
    conn = init_db()
    cur = conn.cursor()
    since = datetime.now(KST) - timedelta(days=2)
    raw_items = []

    for feed in RSS_FEEDS:
        d = feedparser.parse(feed)
        for e in d.entries:
            title = e.get("title","").strip()
            link = normalize_url(e.get("link","").strip())
            if not title or not link:
                continue
            published = None
            for k in ("published_parsed","updated_parsed"):
                if getattr(e, k, None):
                    import time as _t
                    published = datetime.fromtimestamp(_t.mktime(getattr(e,k)), tz=tz.UTC).astimezone(KST)
                    break
            if published and published < since:
                continue
            summary_hint = (e.get("summary","") or "")
            if not simple_kw_match(title, summary_hint):
                continue
            raw_items.append({"title":title, "url":link, "published":published, "summary_hint":summary_hint})

    prepared = []
    for it in raw_items:
        content = fetch_article(it["url"]) or it["summary_hint"]
        chash = hashlib.sha1((content[:4000]).encode("utf-8","ignore")).hexdigest() if content else ""
        prepared.append({
            "title": it["title"],
            "url": it["url"],
            "published": it["published"],
            "content_hash": chash,
            "content": content
        })

    deduped = []
    for it in prepared:
        cur.execute("SELECT 1 FROM items WHERE url = ?", (it["url"],))
        if cur.fetchone(): 
            continue
        if it["content_hash"]:
            cur.execute("SELECT 1 FROM items WHERE content_hash = ?", (it["content_hash"],))
            if cur.fetchone():
                continue
        if any(similar(it["title"], d["title"]) >= 80 for d in deduped):
            continue
        deduped.append(it)

    for it in deduped:
        it["summary"] = summarize_text(it["content"], sent_count=2)

    deduped.sort(key=lambda x: x["published"] or datetime.now(KST), reverse=True)
    blocks = build_blocks(deduped[:15])
    post_to_slack(blocks)

    for it in deduped:
        cur.execute("INSERT OR IGNORE INTO items(url,title,content_hash,published_kst) VALUES (?,?,?,?)",
                    (it["url"], it["title"], it["content_hash"], (it["published"] or datetime.now(KST)).isoformat()))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
