#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

MIKAN_BASE = "https://mikanani.me"
DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BugoAnimeTracker/1.1)"}
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts"}
CHINESE_NUM = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
MONTH_TO_SEASON = {
    "1月": "冬",
    "4月": "春",
    "7月": "夏",
    "10月": "秋",
    "spring": "春",
    "summer": "夏",
    "autumn": "秋",
    "fall": "秋",
    "winter": "冬",
    "春": "春",
    "夏": "夏",
    "秋": "秋",
    "冬": "冬",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def print_json(obj: Any) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item is None:
            continue
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def normalize_name(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"第\s*[一二三四五六七八九十0-9]+\s*季", "", text)
    text = re.sub(r"season\s*\d+", "", text, flags=re.I)
    text = re.sub(r"s\d{1,2}", "", text, flags=re.I)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text


def sanitize_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', ' ', name).strip()


def is_video_file(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in VIDEO_EXTS


def chinese_number_to_int(text: str) -> Optional[int]:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if len(text) == 1 and text in CHINESE_NUM:
        return CHINESE_NUM[text]
    if text.startswith("十") and len(text) == 2 and text[1] in CHINESE_NUM:
        return 10 + CHINESE_NUM[text[1]]
    if len(text) == 2 and text[0] in CHINESE_NUM and text[1] == "十":
        return CHINESE_NUM[text[0]] * 10
    if len(text) == 3 and text[0] in CHINESE_NUM and text[1] == "十" and text[2] in CHINESE_NUM:
        return CHINESE_NUM[text[0]] * 10 + CHINESE_NUM[text[2]]
    return None


def extract_season_number(text: str) -> Optional[int]:
    m = re.search(r"第\s*([一二三四五六七八九十0-9]+)\s*季", text)
    if m:
        return chinese_number_to_int(m.group(1))
    m = re.search(r"season\s*(\d+)", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\bs(\d{1,2})\b", text, re.I)
    if m:
        return int(m.group(1))
    return None


def extract_episode_number(text: str) -> Optional[int]:
    patterns = [
        r"第\s*(\d{1,3})\s*[话話集]",
        r"[\[【](\d{1,3})(?:v\d+)?[\]】]",
        r"\bep?\s*(\d{1,3})\b",
        r"\be(\d{1,3})\b",
        r"\b(\d{1,3})v\d+\b",
        r"(?:^|[^\d])(\d{1,3})(?:[^\d]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                val = int(m.group(1))
            except ValueError:
                continue
            if 0 < val < 1000:
                return val
    return None


def build_aliases(name: str, resolved_title: str) -> List[str]:
    aliases = [name, resolved_title]
    base = re.sub(r"第\s*[一二三四五六七八九十0-9]+\s*季", "", resolved_title).strip()
    if base != resolved_title:
        aliases.append(base)
    return unique_keep_order(aliases)


class TrackerError(Exception):
    pass


class StateStore:
    def __init__(self, path: str):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._empty_state()
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self._normalize(data)

    def _empty_state(self) -> Dict[str, Any]:
        return {
            "subscriptions": [],
            "seen_items": {},
            "downloaded_items": {},
            "processed_files": {},
            "metadata_cache": {},
            "history": [],
        }

    def _normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        base = self._empty_state()
        base.update(data or {})
        return base

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_history(self, action: str, details: Dict[str, Any]) -> None:
        self.data["history"].append({"ts": now_iso(), "action": action, "details": details})
        self.data["history"] = self.data["history"][-300:]

    def upsert_subscription(self, sub: Dict[str, Any]) -> Dict[str, Any]:
        for idx, item in enumerate(self.data["subscriptions"]):
            if str(item.get("bangumi_id")) == str(sub.get("bangumi_id")):
                merged = dict(item)
                merged.update(sub)
                merged["aliases"] = unique_keep_order((item.get("aliases") or []) + (sub.get("aliases") or []))
                self.data["subscriptions"][idx] = merged
                return merged
        self.data["subscriptions"].append(sub)
        return sub


class MikanClient:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def season_list(self, year: int, season_str: str) -> List[Dict[str, Any]]:
        url = f"{MIKAN_BASE}/Home/BangumiCoverFlowByDayOfWeek"
        resp = self.session.get(url, params={"year": year, "seasonStr": season_str}, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()
        items = []
        for a in soup.select('a[href^="/Home/Bangumi/"]'):
            href = a.get("href", "")
            title = " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue
            m = re.search(r"/Home/Bangumi/(\d+)", href)
            if not m:
                continue
            bangumi_id = m.group(1)
            if bangumi_id in seen:
                continue
            seen.add(bangumi_id)
            items.append({
                "bangumi_id": bangumi_id,
                "title": title,
                "page_url": urljoin(MIKAN_BASE, href),
                "rss_url": f"{MIKAN_BASE}/RSS/Bangumi?bangumiId={bangumi_id}",
            })
        return items

    def search(self, query: str) -> List[Dict[str, Any]]:
        url = f"{MIKAN_BASE}/Home/Search"
        resp = self.session.get(url, params={"searchstr": query}, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()
        items = []
        for a in soup.select('a[href^="/Home/Bangumi/"]'):
            href = a.get("href", "")
            title = " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue
            m = re.search(r"/Home/Bangumi/(\d+)", href)
            if not m:
                continue
            bangumi_id = m.group(1)
            if bangumi_id in seen:
                continue
            seen.add(bangumi_id)
            items.append({
                "bangumi_id": bangumi_id,
                "title": title,
                "page_url": urljoin(MIKAN_BASE, href),
                "rss_url": f"{MIKAN_BASE}/RSS/Bangumi?bangumiId={bangumi_id}",
            })
        return items

    def resolve_bangumi(self, name: str) -> Dict[str, Any]:
        results = self.search(name)
        if not results:
            raise TrackerError(f"未找到番剧: {name}")
        exact = [x for x in results if x["title"] == name]
        return exact[0] if exact else results[0]

    def feed_items(self, rss_url: str, limit: int = 30) -> List[Dict[str, Any]]:
        parsed = feedparser.parse(rss_url)
        items = []
        for entry in parsed.entries[:limit]:
            enclosure_url = None
            if getattr(entry, "enclosures", None):
                enclosure_url = entry.enclosures[0].get("href")
            if not enclosure_url:
                continue
            guid = entry.get("guid") or entry.get("id") or enclosure_url
            items.append({
                "guid": guid,
                "title": entry.get("title", ""),
                "link": entry.get("link"),
                "published": entry.get("published") or entry.get("updated"),
                "torrent_url": enclosure_url,
                "summary": entry.get("summary"),
                "episode": extract_episode_number(entry.get("title", "")),
            })
        return items


class OpenListClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": token,
            **DEFAULT_HEADERS,
        })

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(f"{self.base_url}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add_offline_download(self, path: str, urls: List[str], tool: str, delete_policy: str) -> Dict[str, Any]:
        return self._post("/api/fs/add_offline_download", {
            "path": path,
            "urls": urls,
            "tool": tool,
            "delete_policy": delete_policy,
        })

    def list_dir(self, path: str) -> Dict[str, Any]:
        return self._post("/api/fs/list", {
            "path": path,
            "password": "",
            "page": 1,
            "per_page": 0,
            "refresh": False,
        })

    def mkdir(self, path: str) -> Dict[str, Any]:
        return self._post("/api/fs/mkdir", {"path": path})

    def rename(self, path: str, name: str, overwrite: bool = True) -> Dict[str, Any]:
        return self._post("/api/fs/rename", {"path": path, "name": name, "overwrite": overwrite})

    def move(self, src_dir: str, dst_dir: str, names: List[str], overwrite: bool = False, skip_existing: bool = True) -> Dict[str, Any]:
        return self._post("/api/fs/move", {
            "src_dir": src_dir,
            "dst_dir": dst_dir,
            "names": names,
            "overwrite": overwrite,
            "skip_existing": skip_existing,
        })

    def put_text(self, file_path: str, text: str, overwrite: bool = True) -> Dict[str, Any]:
        resp = self.session.put(
            f"{self.base_url}/api/fs/put",
            data=text.encode("utf-8"),
            headers={
                "File-Path": file_path,
                "Password": "",
                "Overwrite": "true" if overwrite else "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def ensure_dir(self, path: str) -> None:
        current = ""
        for part in PurePosixPath(path).parts:
            if part == "/":
                current = "/"
                continue
            if current in {"", "/"}:
                current = f"/{part}"
            else:
                current = f"{current}/{part}"
            self.mkdir(current)




class JikanClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def search(self, query: str) -> Optional[Dict[str, Any]]:
        resp = self.session.get("https://api.jikan.moe/v4/anime", params={"q": query, "limit": 5}, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if not data:
            return None
        nq = normalize_name(query)
        best = None
        best_score = -1
        for item in data:
            names = unique_keep_order([
                item.get("title"),
                item.get("title_english"),
                item.get("title_japanese"),
                *item.get("titles", []),
            ])
            score = 0
            for raw in names:
                if isinstance(raw, dict):
                    raw = raw.get("title")
                nn = normalize_name(str(raw or ""))
                if not nn:
                    continue
                if nn == nq:
                    score = max(score, 100)
                elif nq and nq in nn:
                    score = max(score, 90)
                elif nn and nn in nq:
                    score = max(score, 80)
            if score > best_score:
                best = item
                best_score = score
        return best or data[0]


def normalize_season(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        raise TrackerError("缺少季节或月份")
    mapped = MONTH_TO_SEASON.get(raw)
    if mapped:
        return mapped
    raise TrackerError(f"无法识别的季节或月份: {value}")


def get_openlist_client() -> Optional[OpenListClient]:
    base = os.getenv("BUGO_OPENLIST_BASE_URL", "").strip()
    token = os.getenv("BUGO_OPENLIST_TOKEN", "").strip()
    if base and token:
        return OpenListClient(base, token)
    return None




def parse_names_env(env_name: str = "BUGO_ANIME_NAMES") -> List[str]:
    raw = os.getenv(env_name, "")
    parts = [x.strip() for x in raw.replace("\r", "").split("\n")]
    return [x for x in parts if x]


def metadata_for_title(store: StateStore, title: str) -> Optional[Dict[str, Any]]:
    cache = store.data.setdefault("metadata_cache", {})
    key = normalize_name(title)
    if key in cache:
        return cache[key]
    query = re.sub(r"第\s*[一二三四五六七八九十0-9]+\s*季", "", title).strip()
    query = re.sub(r"season\s*\d+", "", query, flags=re.I).strip()
    data = JikanClient().search(query)
    if not data:
        item = {"title": title, "source": "fallback"}
        cache[key] = item
        return item
    normalized_query = normalize_name(query)
    candidate_titles = unique_keep_order([
        data.get("title"),
        data.get("title_english"),
        data.get("title_japanese"),
        *[(x or {}).get("title") for x in (data.get("titles") or [])],
    ])
    chosen_title = title
    for cand in candidate_titles:
        nc = normalize_name(cand)
        if nc == normalized_query or (normalized_query and normalized_query in nc) or (nc and nc in normalized_query):
            chosen_title = cand
            break
    item = {
        "title": chosen_title or title,
        "title_english": data.get("title_english"),
        "title_japanese": data.get("title_japanese"),
        "year": data.get("year"),
        "synopsis": data.get("synopsis"),
        "genres": [g.get("name") for g in (data.get("genres") or []) if g.get("name")],
        "aired_from": ((data.get("aired") or {}).get("from") or "")[:10],
        "url": data.get("url"),
        "source": "jikan",
    }
    cache[key] = item
    return item


def score_subscription_match(filename: str, sub: Dict[str, Any]) -> int:
    nf = normalize_name(filename)
    best = 0
    for alias in unique_keep_order((sub.get("aliases") or []) + [sub.get("title")]):
        na = normalize_name(alias)
        if not na:
            continue
        if na in nf:
            best = max(best, len(na))
    return best


def find_subscription_for_file(filename: str, subscriptions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ranked = []
    for sub in subscriptions:
        score = score_subscription_match(filename, sub)
        if score > 0:
            ranked.append((score, sub))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def make_tvshow_nfo(display_title: str, metadata: Optional[Dict[str, Any]]) -> str:
    title = metadata.get("title") if metadata else display_title
    original = (metadata or {}).get("title_japanese") or ""
    year = (metadata or {}).get("year") or ""
    plot = (metadata or {}).get("synopsis") or ""
    premiered = (metadata or {}).get("aired_from") or ""
    genres = (metadata or {}).get("genres") or []
    website = (metadata or {}).get("url") or ""
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<tvshow>",
        f"  <title>{escape(title)}</title>",
    ]
    if original:
        lines.append(f"  <originaltitle>{escape(original)}</originaltitle>")
    if year:
        lines.append(f"  <year>{escape(str(year))}</year>")
    if premiered:
        lines.append(f"  <premiered>{escape(premiered)}</premiered>")
    if plot:
        lines.append(f"  <plot>{escape(plot)}</plot>")
    for genre in genres:
        lines.append(f"  <genre>{escape(genre)}</genre>")
    if website:
        lines.append(f"  <id>{escape(website)}</id>")
    lines.append("</tvshow>")
    return "\n".join(lines) + "\n"


def make_episode_nfo(show_title: str, season_num: int, episode_num: int, release_title: str) -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<episodedetails>\n"
        f"  <title>{escape(release_title)}</title>\n"
        f"  <showtitle>{escape(show_title)}</showtitle>\n"
        f"  <season>{season_num}</season>\n"
        f"  <episode>{episode_num}</episode>\n"
        "</episodedetails>\n"
    )


def related_seen_guids(store: StateStore, bangumi_id: str, filename: str, episode_num: Optional[int]) -> List[str]:
    nf = normalize_name(filename)
    matched = []
    for guid, item in store.data.get("seen_items", {}).items():
        if str(item.get("bangumi_id")) != str(bangumi_id):
            continue
        if guid in store.data.get("downloaded_items", {}):
            continue
        title = item.get("title", "")
        item_ep = item.get("episode") or extract_episode_number(title)
        if episode_num and item_ep == episode_num:
            matched.append(guid)
            continue
        nt = normalize_name(title)
        if nt and (nt in nf or nf in nt):
            matched.append(guid)
    return matched


def command_season_list(store: StateStore, mikan: MikanClient) -> Dict[str, Any]:
    year = int(os.getenv("BUGO_YEAR", str(datetime.now().year)))
    season = normalize_season(os.getenv("BUGO_SEASON", ""))
    exclude_subscribed = os.getenv("BUGO_EXCLUDE_SUBSCRIBED", "0").strip().lower() in {"1", "true", "yes"}
    items = mikan.season_list(year, season)
    subscribed_ids = {str(x.get("bangumi_id")) for x in store.data["subscriptions"]}
    if exclude_subscribed:
        items = [x for x in items if str(x.get("bangumi_id")) not in subscribed_ids]
    store.add_history("season-list", {"year": year, "season": season, "count": len(items), "exclude_subscribed": exclude_subscribed})
    store.save()
    return {"ok": True, "year": year, "season": season, "count": len(items), "items": items}


def command_search(store: StateStore, mikan: MikanClient) -> Dict[str, Any]:
    query = os.getenv("BUGO_QUERY", "").strip()
    if not query:
        raise TrackerError("BUGO_QUERY is required")
    items = mikan.search(query)
    store.add_history("search", {"query": query, "count": len(items)})
    store.save()
    return {"ok": True, "query": query, "count": len(items), "items": items}


def command_subscribe(store: StateStore, mikan: MikanClient) -> Dict[str, Any]:
    names = parse_names_env("BUGO_ANIME_NAMES")
    if not names:
        raise TrackerError("BUGO_ANIME_NAMES is required")
    subgroup = os.getenv("BUGO_DEFAULT_SUBGROUP", "").strip() or None
    subgroup_preference = parse_names_env("BUGO_SUBGROUP_PREFERENCE")
    items = []
    for name in names:
        resolved = mikan.resolve_bangumi(name)
        rss_url = resolved["rss_url"]
        if subgroup:
            rss_url = f"{rss_url}&subgroupid={quote(subgroup)}"
        sub = {
            "bangumi_id": resolved["bangumi_id"],
            "title": resolved["title"],
            "page_url": resolved["page_url"],
            "rss_url": rss_url,
            "subgroup_id": subgroup,
            "subgroup_preference": subgroup_preference,
            "aliases": build_aliases(name, resolved["title"]),
            "season_num": extract_season_number(resolved["title"]) or 1,
            "created_at": now_iso(),
            "active": True,
        }
        items.append(store.upsert_subscription(sub))
    store.add_history("subscribe", {"count": len(items), "names": names})
    store.save()
    return {"ok": True, "count": len(items), "items": items}


def command_list_subscriptions(store: StateStore) -> Dict[str, Any]:
    return {"ok": True, "count": len(store.data["subscriptions"]), "items": store.data["subscriptions"]}


def detect_subgroup(title: str) -> str:
    title = (title or "").strip()
    m = re.match(r"^[\[【]([^\]】]+)[\]】]", title)
    if m:
        return m.group(1).strip()
    return "unknown"


def release_priority(item: Dict[str, Any], preferred_quality_re: Optional[str], subgroup_preference: List[str]) -> Tuple[int, int, int, int, str]:
    title = item.get("title", "")
    subgroup = detect_subgroup(title)
    subgroup_score = 0
    lowered_subgroup = subgroup.lower()
    for idx, pref in enumerate(subgroup_preference):
        if pref.lower() == lowered_subgroup:
            subgroup_score = 1000 - idx
            break
    quality_score = 0
    if re.search(r"1080", title, re.I):
        quality_score += 200
    elif re.search(r"720", title, re.I):
        quality_score += 100
    if re.search(r"hevc|x265|10bit", title, re.I):
        quality_score += 30
    if re.search(r"简|gb|chs", title, re.I):
        quality_score += 20
    if re.search(r"繁|big5|cht", title, re.I):
        quality_score += 10
    preferred_score = 0
    if preferred_quality_re:
        try:
            if re.search(preferred_quality_re, title, re.I):
                preferred_score = 500
        except re.error:
            preferred_score = 0
    published = item.get("published") or ""
    return (subgroup_score, preferred_score, quality_score, len(title), published)


def dedupe_feed_items(items: List[Dict[str, Any]], preferred_quality_re: Optional[str], subgroup_preference: List[str]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    passthrough: List[Dict[str, Any]] = []
    for item in items:
        ep = item.get("episode")
        if ep is None:
            passthrough.append(item)
            continue
        grouped.setdefault(str(ep), []).append(item)
    selected: List[Dict[str, Any]] = []
    for ep, group in grouped.items():
        group = sorted(group, key=lambda x: release_priority(x, preferred_quality_re, subgroup_preference), reverse=True)
        selected.append(group[0])
    selected.extend(passthrough)
    selected.sort(key=lambda x: ((x.get("episode") is None), x.get("episode") or 0, x.get("published") or ""))
    return selected


def pick_feed_items(items: List[Dict[str, Any]], preferred_quality_re: Optional[str], subgroup_preference: List[str]) -> List[Dict[str, Any]]:
    deduped = dedupe_feed_items(items, preferred_quality_re, subgroup_preference)
    return deduped


def command_check_updates(store: StateStore, mikan: MikanClient) -> Dict[str, Any]:
    limit = int(os.getenv("BUGO_CHECK_LIMIT", "30"))
    queue_backend = "openlist"

    new_items = []
    for sub in store.data["subscriptions"]:
        if not sub.get("active", True):
            continue
        feed_items = mikan.feed_items(sub["rss_url"], limit=limit)
        pending = []
        for item in feed_items:
            if item["guid"] in store.data["downloaded_items"]:
                continue
            existing = store.data["seen_items"].get(item["guid"], {})
            if existing.get("queued"):
                continue
            pending.append(item)
        for item in pending:
            existing = dict(store.data["seen_items"].get(item["guid"], {}))
            record = dict(existing)
            record.update({
                "guid": item["guid"],
                "title": item["title"],
                "bangumi_id": sub["bangumi_id"],
                "published_at": item.get("published"),
                "torrent_url": item["torrent_url"],
                "episode": item.get("episode"),
                "first_seen_at": existing.get("first_seen_at") or now_iso(),
                "last_checked_at": now_iso(),
                "queued": existing.get("queued", False),
                "queue_result": existing.get("queue_result"),
                "queue_backend": existing.get("queue_backend") or queue_backend,
            })
            store.data["seen_items"][item["guid"]] = record
            new_items.append({
                **item,
                "bangumi_id": sub["bangumi_id"],
                "bangumi_title": sub["title"],
                "queued": record["queued"],
                "queue_result": record["queue_result"],
                "queue_backend": record["queue_backend"],
                "subgroup": detect_subgroup(item.get("title", "")),
            })
    store.add_history("check-updates", {"count": len(new_items), "mode": "inspect_only", "backend": queue_backend})
    store.save()
    return {"ok": True, "count": len(new_items), "items": new_items, "queue_results": [], "queue_backend": queue_backend, "mode": "inspect_only"}


def command_queue_downloads(store: StateStore) -> Dict[str, Any]:
    openlist = get_openlist_client()
    if not openlist:
        raise TrackerError("missing OpenList credentials")
    raw = os.getenv("BUGO_QUERY", "").strip()
    if not raw:
        raise TrackerError("BUGO_QUERY is required and should contain one or more GUIDs or torrent URLs separated by newlines")
    download_dir = os.getenv("BUGO_DOWNLOAD_DIR", "/media/downloaded")
    tool = os.getenv("BUGO_OPENLIST_TOOL", "qBittorrent")
    delete_policy = os.getenv("BUGO_OPENLIST_DELETE_POLICY", "delete_on_upload_succeed")
    queue_backend = "openlist"

    refs = [x.strip() for x in raw.replace("\r", "").split("\n") if x.strip()]
    queued_items = []
    for ref in refs:
        existing = dict(store.data.get("seen_items", {}).get(ref, {}))
        guid = existing.get("guid") or ref
        torrent_url = existing.get("torrent_url") or (ref if ref.startswith("http://") or ref.startswith("https://") else None)
        title = existing.get("title") or guid
        if not torrent_url:
            raise TrackerError(f"missing torrent url for: {ref}")
        if existing.get("queued"):
            queued_items.append({
                "guid": guid,
                "title": title,
                "ok": True,
                "skipped": True,
                "reason": "already_queued",
                "result": existing.get("queue_result"),
                "backend": existing.get("queue_backend") or queue_backend,
            })
            continue
        result = openlist.add_offline_download(download_dir, [torrent_url], tool=tool, delete_policy=delete_policy)
        updated = dict(existing)
        updated.update({
            "guid": guid,
            "title": title,
            "torrent_url": torrent_url,
            "last_checked_at": now_iso(),
            "queued": bool(result.get("code") == 200),
            "queue_result": result,
            "queue_backend": queue_backend,
        })
        store.data.setdefault("seen_items", {})[guid] = updated
        queued_items.append({
            "guid": guid,
            "title": title,
            "ok": updated["queued"],
            "result": result,
            "backend": queue_backend,
        })
    store.add_history("queue-downloads", {"count": len(queued_items), "backend": queue_backend})
    store.save()
    return {"ok": True, "count": len(queued_items), "items": queued_items, "queue_results": queued_items, "queue_backend": queue_backend}


def command_mark_downloaded(store: StateStore) -> Dict[str, Any]:
    raw = os.getenv("BUGO_QUERY", "").strip()
    if not raw:
        raise TrackerError("BUGO_QUERY is required and should contain one or more GUIDs separated by newlines")
    guids = [x.strip() for x in raw.replace("\r", "").split("\n") if x.strip()]
    note = os.getenv("BUGO_SEASON", "").strip() or None
    out = []
    for guid in guids:
        seen = store.data["seen_items"].get(guid, {})
        item = {
            "guid": guid,
            "title": seen.get("title", guid),
            "bangumi_id": seen.get("bangumi_id"),
            "marked_at": now_iso(),
            "note": note,
        }
        store.data["downloaded_items"][guid] = item
        out.append(item)
    store.add_history("mark-downloaded", {"count": len(out)})
    store.save()
    return {"ok": True, "count": len(out), "items": out}


def command_inspect_openlist() -> Dict[str, Any]:
    openlist = get_openlist_client()
    if not openlist:
        raise TrackerError("missing OpenList credentials")
    path = os.getenv("BUGO_OPENLIST_PATH", "/")
    result = openlist.list_dir(path)
    return {"ok": True, "path": path, "result": result}


def process_files(store: StateStore, openlist: OpenListClient, source_dir: str, library_dir: str, only_names: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
    listing = openlist.list_dir(source_dir)
    content = (((listing or {}).get("data") or {}).get("content") or [])
    only_set = set(only_names or [])
    processed = []
    skipped = []
    for item in content:
        name = item.get("name", "")
        if item.get("is_dir"):
            continue
        if only_set and name not in only_set:
            continue
        if not is_video_file(name):
            skipped.append({"name": name, "reason": "not_video"})
            continue
        source_key = f"{source_dir.rstrip('/')}/{name}"
        if source_key in store.data.get("processed_files", {}):
            skipped.append({"name": name, "reason": "already_processed"})
            continue
        sub = find_subscription_for_file(name, store.data["subscriptions"])
        if not sub:
            skipped.append({"name": name, "reason": "no_subscription_match"})
            continue
        episode_num = extract_episode_number(name)
        season_num = int(sub.get("season_num") or extract_season_number(sub.get("title", "")) or 1)
        metadata = metadata_for_title(store, sub.get("title", ""))
        show_title = sanitize_name((metadata or {}).get("title") or sub.get("title") or "Unknown Anime")
        show_dir = f"{library_dir.rstrip('/')}/{show_title}"
        season_dir = f"{show_dir}/Season {season_num}"
        ext = PurePosixPath(name).suffix
        if episode_num:
            target_name = sanitize_name(f"{show_title} - S{season_num:02d}E{episode_num:02d}{ext}")
            episode_nfo_name = sanitize_name(f"{show_title} - S{season_num:02d}E{episode_num:02d}.nfo")
        else:
            target_name = sanitize_name(name)
            episode_nfo_name = None
        target_path = f"{season_dir}/{target_name}"
        related_guids = related_seen_guids(store, str(sub.get("bangumi_id")), name, episode_num)

        if not dry_run:
            openlist.ensure_dir(show_dir)
            openlist.ensure_dir(season_dir)
            openlist.move(source_dir, season_dir, [name], overwrite=False, skip_existing=True)
            if target_name != name:
                openlist.rename(f"{season_dir}/{name}", target_name, overwrite=True)
            openlist.put_text(f"{show_dir}/tvshow.nfo", make_tvshow_nfo(show_title, metadata), overwrite=True)
            if episode_nfo_name and episode_num:
                openlist.put_text(f"{season_dir}/{episode_nfo_name}", make_episode_nfo(show_title, season_num, episode_num, name), overwrite=True)

        processed_entry = {
            "source": source_key,
            "target": target_path,
            "name": name,
            "show_title": show_title,
            "season": season_num,
            "episode": episode_num,
            "bangumi_id": sub.get("bangumi_id"),
            "processed_at": now_iso(),
            "related_guids": related_guids,
            "dry_run": dry_run,
        }
        store.data.setdefault("processed_files", {})[source_key] = processed_entry
        for guid in related_guids:
            seen = store.data.get("seen_items", {}).get(guid, {})
            store.data.setdefault("downloaded_items", {})[guid] = {
                "guid": guid,
                "title": seen.get("title", guid),
                "bangumi_id": seen.get("bangumi_id"),
                "marked_at": now_iso(),
                "note": f"organized from {source_key}",
                "target": target_path,
            }
        processed.append(processed_entry)
    store.add_history("process-downloads", {"source_dir": source_dir, "count": len(processed), "dry_run": dry_run})
    store.save()
    return {"ok": True, "source_dir": source_dir, "count": len(processed), "processed": processed, "skipped": skipped}


def command_process_downloads(store: StateStore) -> Dict[str, Any]:
    openlist = get_openlist_client()
    if not openlist:
        raise TrackerError("missing OpenList credentials")
    source_dir = os.getenv("BUGO_ORGANIZE_FROM", os.getenv("BUGO_DOWNLOAD_DIR", "/media/downloaded"))
    library_dir = os.getenv("BUGO_LIBRARY_DIR", "/media/data")
    dry_run = os.getenv("BUGO_ORGANIZE_DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}
    only_names = parse_names_env("BUGO_PROCESS_ONLY_NAMES")
    return process_files(store, openlist, source_dir, library_dir, only_names=only_names or None, dry_run=dry_run)


def extract_strings(value: Any) -> List[str]:
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(extract_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(extract_strings(v))
    return out


def command_handle_callback(store: StateStore) -> Dict[str, Any]:
    payload_raw = os.getenv("BUGO_CALLBACK_PAYLOAD", "").strip()
    names = parse_names_env("BUGO_PROCESS_ONLY_NAMES")
    if payload_raw:
        try:
            payload = json.loads(payload_raw)
            strings = extract_strings(payload)
            for s in strings:
                base = PurePosixPath(s).name
                if is_video_file(base):
                    names.append(base)
        except json.JSONDecodeError:
            pass
    names = unique_keep_order(names)
    if not names:
        raise TrackerError("callback payload did not include recognizable video names")
    openlist = get_openlist_client()
    if not openlist:
        raise TrackerError("missing OpenList credentials")
    source_dir = os.getenv("BUGO_ORGANIZE_FROM", os.getenv("BUGO_DOWNLOAD_DIR", "/media/downloaded"))
    library_dir = os.getenv("BUGO_LIBRARY_DIR", "/media/data")
    dry_run = os.getenv("BUGO_ORGANIZE_DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}
    result = process_files(store, openlist, source_dir, library_dir, only_names=names, dry_run=dry_run)
    result["callback_names"] = names
    return result


def main() -> None:
    try:
        cmd = os.getenv("BUGO_ANIME_CMD", "").strip()
        state_path = os.getenv("BUGO_STATE_PATH", "").strip()
        if not cmd:
            raise TrackerError("missing BUGO_ANIME_CMD")
        if not state_path:
            raise TrackerError("missing BUGO_STATE_PATH")
        store = StateStore(state_path)
        mikan = MikanClient()

        if cmd == "season-list":
            result = command_season_list(store, mikan)
        elif cmd == "search":
            result = command_search(store, mikan)
        elif cmd == "subscribe":
            result = command_subscribe(store, mikan)
        elif cmd == "list-subscriptions":
            result = command_list_subscriptions(store)
        elif cmd == "check-updates":
            result = command_check_updates(store, mikan)
        elif cmd == "mark-downloaded":
            result = command_mark_downloaded(store)
        elif cmd == "queue-downloads":
            result = command_queue_downloads(store)
        elif cmd == "inspect-openlist":
            result = command_inspect_openlist()
        elif cmd == "process-downloads":
            result = command_process_downloads(store)
        elif cmd == "handle-callback":
            result = command_handle_callback(store)
        else:
            raise TrackerError(f"unknown command: {cmd}")
        print_json(result)
    except TrackerError as exc:
        print_json({"ok": False, "error": str(exc), "error_code": "TRACKER_ERROR"})
        sys.exit(1)
    except requests.HTTPError as exc:
        detail = None
        if exc.response is not None:
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
        print_json({"ok": False, "error": str(exc), "detail": detail, "error_code": "HTTP_ERROR"})
        sys.exit(1)
    except Exception as exc:
        print_json({"ok": False, "error": str(exc), "error_code": "UNEXPECTED_ERROR"})
        sys.exit(1)


if __name__ == "__main__":
    main()
