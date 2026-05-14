#!/usr/bin/env python3
import datetime as dt
import email.utils
import hashlib
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"
CACHE_DIR = ROOT / ".cache"
DATA_DIR = ROOT / ".data"
SETTINGS_PATH = DATA_DIR / "settings.json"
LIBRARY_PATH = DATA_DIR / "library.json"
QWEN_CONFIG_PATH = DATA_DIR / "qwen.json"

APP_VERSION = "0.1.0"
CACHE_VERSION = 2
PROMPT_VERSION = 3
ARXIV_COOLDOWN_PATH = CACHE_DIR / "arxiv_cooldown.json"
ARXIV_PAGE_SIZE = 25
ARXIV_PAGE_DELAY_SECONDS = 3.2
ARXIV_RATE_LIMIT_COOLDOWN_SECONDS = 20 * 60
APP_TIMEZONE_NAME = "Asia/Shanghai"
APP_TIMEZONE = dt.timezone(dt.timedelta(hours=8), APP_TIMEZONE_NAME)

DEFAULT_KEYWORDS = [
    "robotics",
    "embodied intelligence",
    "vision language action",
    "VLA",
    "manipulation",
    "navigation",
]

DEFAULT_SETTINGS = {
    "keywords": DEFAULT_KEYWORDS,
    "maxResults": 100,
}

SECTIONS = [
    {
        "id": "all",
        "label": "日期总览",
        "description": "选定北京时间自然日内关键词命中的全部论文。",
    },
    {
        "id": "model_training",
        "label": "模型/训练",
        "description": "具身模型、VLA、预训练、后训练、RL、模仿学习、世界模型和策略学习。",
    },
    {
        "id": "data_collection",
        "label": "数据/采集",
        "description": "多源数据、真机数据、Ego/UMI、DAgger、遥操作、仿真数据和数据工程。",
    },
    {
        "id": "manipulation",
        "label": "移动/灵巧操作",
        "description": "移动操作、灵巧操作、灵巧手、抓取、接触丰富操作、长程任务和控制。",
    },
    {
        "id": "embodiment_system",
        "label": "本体/系统",
        "description": "机器人本体、灵巧手、末端执行器、传感器、手眼系统、端侧计算和真机部署。",
    },
    {
        "id": "reasoning_safety",
        "label": "推理/规划/安全",
        "description": "具身推理、空间推理、任务规划、affordance、记忆、约束、安全和失败恢复。",
    },
    {
        "id": "sim_eval_repro",
        "label": "仿真/评测/复现",
        "description": "仿真平台、benchmark、sim2real、评测协议、指标、开源代码和复现实用性。",
    },
]

SECTION_TERMS = {
    "model_training": [
        "vision-language-action",
        "vision language action",
        "vla",
        "vlm",
        "vision-language model",
        "vision language model",
        "embodied model",
        "embodied agent",
        "foundation model",
        "multimodal",
        "large language model",
        "llm",
        "world model",
        "language-conditioned",
        "action model",
        "policy",
        "diffusion policy",
        "flow policy",
        "action tokenizer",
        "action chunk",
        "pretraining",
        "pre-training",
        "post-training",
        "post training",
        "reinforcement learning",
        "offline reinforcement learning",
        "offline-to-online",
        "rl",
        "imitation learning",
        "behavior cloning",
        "behaviour cloning",
        "fine-tuning",
        "alignment",
        "moe",
    ],
    "data_collection": [
        "dataset",
        "data collection",
        "data engine",
        "multi-source",
        "multisource",
        "real-world data",
        "real robot data",
        "in-the-wild",
        "egocentric",
        "ego",
        "umi",
        "universal manipulation interface",
        "teleoperation",
        "tele-operated",
        "teleoperated",
        "demonstration",
        "human demonstration",
        "dagger",
        "annotation",
        "labeling",
        "synthetic data",
        "trajectory dataset",
        "robot data",
    ],
    "manipulation": [
        "mobile manipulation",
        "manipulation",
        "manipulator",
        "grasp",
        "grasping",
        "dexterous",
        "dexterous hand",
        "robot hand",
        "hand pose",
        "bimanual",
        "dual-arm",
        "contact-rich",
        "force control",
        "whole-body",
        "control",
        "trajectory",
        "planning",
        "locomotion",
        "navigation",
        "long-horizon",
        "task execution",
    ],
    "embodiment_system": [
        "robot body",
        "embodiment",
        "hardware",
        "end-effector",
        "end effector",
        "gripper",
        "dexterous hand",
        "robot hand",
        "tactile",
        "sensor",
        "camera",
        "head-mounted",
        "egocentric camera",
        "actuator",
        "real-time",
        "onboard",
        "edge",
        "deployment",
        "system integration",
        "arm",
        "humanoid",
        "mobile robot",
    ],
    "reasoning_safety": [
        "reasoning",
        "spatial reasoning",
        "task planning",
        "planner",
        "affordance",
        "memory",
        "constraint",
        "safe",
        "safety",
        "failure",
        "recovery",
        "verification",
        "temporal logic",
        "ltl",
        "controllable",
        "interpretable",
        "explainable",
        "risk",
        "robustness",
    ],
    "sim_eval_repro": [
        "benchmark",
        "benchmarks",
        "evaluation",
        "metric",
        "simulator",
        "simulation",
        "sim-to-real",
        "sim2real",
        "testbed",
        "leaderboard",
        "open-source",
        "open source",
        "code",
        "github",
        "implementation",
        "reproduce",
        "reproducible",
        "reproduction",
        "toolkit",
        "framework",
    ],
}

PRIMARY_SECTION_TERMS = {
    "model_training": [
        "vision-language-action",
        "vision language action",
        "vla",
        "world model",
        "policy",
        "reinforcement learning",
        "imitation learning",
        "behavior cloning",
        "pretraining",
        "pre-training",
        "post-training",
        "fine-tuning",
        "diffusion policy",
        "flow policy",
    ],
    "data_collection": [
        "dataset",
        "data collection",
        "data engine",
        "demonstration",
        "teleoperation",
        "egocentric",
        "ego",
        "umi",
        "universal manipulation interface",
        "real-world data",
        "real robot data",
        "in-the-wild",
        "dagger",
        "trajectory dataset",
    ],
    "manipulation": [
        "mobile manipulation",
        "dexterous manipulation",
        "dexterous",
        "grasp",
        "contact-rich",
        "bimanual",
        "dual-arm",
        "whole-body",
        "motion planning",
        "path planning",
        "manipulation task",
        "robot hand",
        "hand pose",
    ],
    "embodiment_system": [
        "robot body",
        "hardware",
        "humanoid",
        "teleoperation",
        "dexterous hand",
        "robot hand",
        "end-effector",
        "gripper",
        "tactile",
        "sensor",
        "head-mounted",
        "camera",
        "imu",
        "onboard",
        "real-time",
        "deployment",
    ],
    "reasoning_safety": [
        "reasoning",
        "spatial intelligence",
        "spatial reasoning",
        "task planning",
        "planner",
        "affordance",
        "constraint",
        "safe",
        "safety",
        "failure",
        "recovery",
        "temporal logic",
        "property-driven",
        "manifold",
        "sampling",
    ],
    "sim_eval_repro": [
        "simulation",
        "simulator",
        "sim-to-real",
        "sim2real",
        "benchmark",
        "evaluation",
        "metric",
        "reproducible",
        "reproduction",
        "open-source",
        "source code",
        "docker",
        "framework",
        "toolkit",
    ],
}

PRIMARY_SECTION_ORDER = [
    "model_training",
    "data_collection",
    "manipulation",
    "embodiment_system",
    "reasoning_safety",
    "sim_eval_repro",
]

ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivRateLimitError(RuntimeError):
    def __init__(self, message, cooldown_seconds=ARXIV_RATE_LIMIT_COOLDOWN_SECONDS):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds

jobs = {}
jobs_lock = threading.Lock()
library_lock = threading.Lock()
settings_lock = threading.RLock()
qwen_lock = threading.RLock()


def utc_datetime():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def utc_now():
    return utc_datetime().isoformat()


def ensure_dirs():
    (CACHE_DIR / "arxiv_pool").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "date_papers").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "qwen_summaries").mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.%s.tmp" % (path.name, uuid.uuid4().hex))
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except json.JSONDecodeError:
        return fallback


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def retry_after_seconds(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        return max(0, int(text))
    except ValueError:
        pass
    try:
        retry_time = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(tzinfo=dt.timezone.utc)
    return max(0, int((retry_time.astimezone(dt.timezone.utc) - utc_datetime()).total_seconds()))


def read_arxiv_cooldown():
    payload = read_json(ARXIV_COOLDOWN_PATH, None)
    if not isinstance(payload, dict):
        return None
    until = parse_iso_datetime(payload.get("until"))
    if not until:
        return None
    remaining = int((until - utc_datetime()).total_seconds())
    if remaining <= 0:
        return None
    payload["remainingSeconds"] = remaining
    return payload


def write_arxiv_cooldown(reason, seconds=None):
    cooldown_seconds = int(seconds or ARXIV_RATE_LIMIT_COOLDOWN_SECONDS)
    cooldown_seconds = max(60, min(60 * 60, cooldown_seconds))
    payload = {
        "reason": str(reason),
        "startedAt": utc_now(),
        "until": (utc_datetime() + dt.timedelta(seconds=cooldown_seconds)).isoformat(),
    }
    payload["remainingSeconds"] = cooldown_seconds
    atomic_write_json(ARXIV_COOLDOWN_PATH, payload)
    return payload


def clear_arxiv_cooldown():
    try:
        ARXIV_COOLDOWN_PATH.unlink()
    except FileNotFoundError:
        pass


def cooldown_warning(cooldown):
    remaining = int(cooldown.get("remainingSeconds") or 0)
    minutes = max(1, (remaining + 59) // 60)
    reason = str(cooldown.get("reason") or "arXiv 触发限流").rstrip(".。")
    return "%s。已进入冷却，还剩约 %d 分钟；这段时间只读取本地缓存。" % (reason, minutes)


def normalize_keywords(keywords):
    clean = []
    seen = set()
    for keyword in keywords or []:
        text = re.sub(r"\s+", " ", str(keyword).strip())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(text)
    return clean or list(DEFAULT_KEYWORDS)


def load_settings():
    ensure_dirs()
    with settings_lock:
        settings = read_json(SETTINGS_PATH, None)
        if not isinstance(settings, dict):
            settings = dict(DEFAULT_SETTINGS)
            atomic_write_json(SETTINGS_PATH, settings)
        settings["keywords"] = normalize_keywords(settings.get("keywords"))
        try:
            settings["maxResults"] = max(1, min(250, int(settings.get("maxResults", 100))))
        except (TypeError, ValueError):
            settings["maxResults"] = 100
        return settings


def save_settings(payload):
    with settings_lock:
        current = load_settings()
        if "keywords" in payload:
            current["keywords"] = normalize_keywords(payload.get("keywords"))
        if "maxResults" in payload:
            try:
                current["maxResults"] = max(1, min(250, int(payload.get("maxResults"))))
            except (TypeError, ValueError):
                pass
        atomic_write_json(SETTINGS_PATH, current)
        return current


def load_library():
    ensure_dirs()
    with library_lock:
        library = read_json(LIBRARY_PATH, None)
        if not isinstance(library, dict):
            library = {"version": 1, "papers": {}}
            atomic_write_json(LIBRARY_PATH, library)
        library.setdefault("version", 1)
        library.setdefault("papers", {})
        return library


def default_library_entry():
    return {
        "favorite": False,
        "status": "unread",
        "category": "",
        "notes": "",
        "updatedAt": None,
    }


def get_library_entries(paper_ids):
    library = load_library()
    papers = library.get("papers", {})
    result = {}
    for paper_id in paper_ids:
        entry = dict(default_library_entry())
        entry.update(papers.get(paper_id, {}))
        result[paper_id] = entry
    return result


def update_library_entry(paper_id, patch):
    allowed_status = {"unread", "queued", "reading", "done"}
    allowed = {"favorite", "status", "category", "notes"}
    with library_lock:
        library = read_json(LIBRARY_PATH, {"version": 1, "papers": {}})
        library.setdefault("version", 1)
        library.setdefault("papers", {})
        entry = dict(default_library_entry())
        entry.update(library["papers"].get(paper_id, {}))
        for key, value in patch.items():
            if key not in allowed:
                continue
            if key == "favorite":
                entry[key] = bool(value)
            elif key == "status":
                entry[key] = value if value in allowed_status else entry[key]
            else:
                entry[key] = str(value or "")
        entry["updatedAt"] = utc_now()
        library["papers"][paper_id] = entry
        atomic_write_json(LIBRARY_PATH, library)
        return entry


def keyword_signature(keywords):
    normalized = sorted([kw.lower() for kw in normalize_keywords(keywords)])
    raw = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "item"


def date_cache_path(date_text, signature):
    return CACHE_DIR / "date_papers" / date_text / (signature + ".json")


def pool_cache_path(signature):
    return CACHE_DIR / "arxiv_pool" / (signature + ".json")


def qwen_section_cache_path(date_text, signature, section):
    return CACHE_DIR / "qwen_summaries" / date_text / signature / ("section_" + safe_name(section) + ".json")


def qwen_paper_cache_path(date_text, signature, paper_id):
    return CACHE_DIR / "qwen_summaries" / date_text / signature / "papers" / (safe_name(paper_id) + ".json")


def parse_date(date_text):
    try:
        return dt.date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("日期必须是 YYYY-MM-DD")


def arxiv_date_range(date_text):
    day = parse_date(date_text)
    local_start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=APP_TIMEZONE)
    local_end = local_start + dt.timedelta(days=1, minutes=-1)
    utc_start = local_start.astimezone(dt.timezone.utc)
    utc_end = local_end.astimezone(dt.timezone.utc)
    return {
        "timezone": APP_TIMEZONE_NAME,
        "startUtc": utc_start.strftime("%Y%m%d%H%M"),
        "endUtc": utc_end.strftime("%Y%m%d%H%M"),
        "startUtcIso": utc_start.isoformat(),
        "endUtcIso": utc_end.isoformat(),
    }


def latest_arxiv_date():
    day = utc_datetime().date() - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def arxiv_term(keyword):
    clean = keyword.replace('"', "").strip()
    if not clean:
        return ""
    if re.search(r"\s", clean):
        return 'all:"%s"' % clean
    return "all:%s" % clean


def build_arxiv_query(date_text, keywords):
    date_range = arxiv_date_range(date_text)
    keyword_terms = [arxiv_term(keyword) for keyword in normalize_keywords(keywords)]
    keyword_terms = [term for term in keyword_terms if term]
    keyword_query = "(" + " OR ".join(keyword_terms) + ")"
    date_query = "submittedDate:[%s TO %s]" % (date_range["startUtc"], date_range["endUtc"])
    return keyword_query + " AND " + date_query


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def strip_arxiv_version(arxiv_id):
    return re.sub(r"v\d+$", "", arxiv_id)


def text_score(text, terms):
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower)


def primary_section_for(text, sections, section_scores):
    if not sections:
        return ""
    primary_scores = {}
    for section in sections:
        weighted = text_score(text, PRIMARY_SECTION_TERMS.get(section, []))
        primary_scores[section] = section_scores.get(section, 0) + weighted * 2
    order_index = {section: index for index, section in enumerate(PRIMARY_SECTION_ORDER)}
    return max(
        sections,
        key=lambda section: (
            primary_scores.get(section, 0),
            section_scores.get(section, 0),
            -order_index.get(section, len(PRIMARY_SECTION_ORDER)),
        ),
    )


def classify_paper(paper, keywords):
    text = " ".join([paper.get("title", ""), paper.get("abstract", ""), " ".join(paper.get("categories", []))])
    lower = text.lower()
    sections = []
    matched_keywords = [kw for kw in normalize_keywords(keywords) if kw.lower() in lower]
    section_scores = {}
    for section, terms in SECTION_TERMS.items():
        score = text_score(text, terms)
        section_scores[section] = score
        if score > 0:
            sections.append(section)
    relevance_score = max(section_scores.values() or [0]) + min(3, len(matched_keywords))
    if not sections and matched_keywords:
        sections.append("model_training")
    if not sections and any(term in lower for term in ["robot", "robotic", "embodied"]):
        sections.append("embodiment_system")
    if not sections:
        sections.append("sim_eval_repro")
    primary_section = primary_section_for(text, sections, section_scores)
    return sections, matched_keywords, relevance_score, primary_section, section_scores


def parse_arxiv_feed(xml_text, keywords):
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall("atom:entry", ARXIV_NS):
        id_url = clean_text(entry.findtext("atom:id", default="", namespaces=ARXIV_NS))
        raw_id = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else id_url
        paper_id = strip_arxiv_version(raw_id)
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ARXIV_NS))
        abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ARXIV_NS))
        published = clean_text(entry.findtext("atom:published", default="", namespaces=ARXIV_NS))
        updated = clean_text(entry.findtext("atom:updated", default="", namespaces=ARXIV_NS))
        authors = [
            clean_text(author.findtext("atom:name", default="", namespaces=ARXIV_NS))
            for author in entry.findall("atom:author", ARXIV_NS)
        ]
        authors = [author for author in authors if author]
        categories = [
            node.attrib.get("term", "")
            for node in entry.findall("atom:category", ARXIV_NS)
            if node.attrib.get("term")
        ]
        primary_node = entry.find("arxiv:primary_category", ARXIV_NS)
        primary_category = primary_node.attrib.get("term", "") if primary_node is not None else (categories[0] if categories else "")
        pdf_url = ""
        abs_url = id_url
        for link in entry.findall("atom:link", ARXIV_NS):
            href = link.attrib.get("href", "")
            title_attr = link.attrib.get("title", "")
            rel = link.attrib.get("rel", "")
            if title_attr == "pdf" or href.endswith(".pdf"):
                pdf_url = href
            if rel == "alternate" and href:
                abs_url = href
        paper = {
            "id": paper_id,
            "versionedId": raw_id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "published": published,
            "updated": updated,
            "submittedDate": published[:10] if published else "",
            "categories": categories,
            "primaryCategory": primary_category,
            "absUrl": abs_url,
            "pdfUrl": pdf_url,
        }
        sections, matched_keywords, score, primary_section, section_scores = classify_paper(paper, keywords)
        paper["sections"] = sections
        paper["primarySection"] = primary_section
        paper["sectionScores"] = section_scores
        paper["matchedKeywords"] = matched_keywords
        paper["relevanceScore"] = score
        papers.append(paper)
    papers.sort(key=lambda item: (item.get("published", ""), item.get("title", "")), reverse=True)
    return papers


def parse_partial_arxiv_feed(xml_bytes, keywords):
    xml_text = xml_bytes.decode("utf-8", errors="replace")
    try:
        return parse_arxiv_feed(xml_text, keywords)
    except ET.ParseError:
        pass
    if "</feed>" in xml_text:
        xml_text = xml_text[: xml_text.rfind("</feed>") + len("</feed>")]
    else:
        last_entry_end = xml_text.rfind("</entry>")
        if last_entry_end < 0:
            raise
        xml_text = xml_text[: last_entry_end + len("</entry>")] + "\n</feed>"
    return parse_arxiv_feed(xml_text, keywords)


def fetch_arxiv_page(url, keywords):
    last_error = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "local-arxiv-workbench/%s (local research tool)" % APP_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                xml_bytes = response.read()
            xml_text = xml_bytes.decode("utf-8", errors="replace")
            return parse_arxiv_feed(xml_text, keywords)
        except http.client.IncompleteRead as exc:
            try:
                page = parse_partial_arxiv_feed(exc.partial or b"", keywords)
            except ET.ParseError as parse_exc:
                last_error = parse_exc
            else:
                if page:
                    return page
                last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            if exc.code == 429:
                detail = (body or "Rate exceeded").rstrip(".。")
                cooldown_seconds = retry_after_seconds(exc.headers.get("Retry-After")) or ARXIV_RATE_LIMIT_COOLDOWN_SECONDS
                raise ArxivRateLimitError("arXiv 触发限流（HTTP 429）：%s。请稍后再加载 arXiv。" % detail, cooldown_seconds)
            last_error = RuntimeError("arXiv HTTP %s：%s" % (exc.code, body or exc.reason))
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
        except (ET.ParseError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
    raise last_error


def fetch_arxiv(date_text, keywords, max_results):
    query = build_arxiv_query(date_text, keywords)
    page_size = min(ARXIV_PAGE_SIZE, max_results)
    api_url = None
    papers_by_id = {}
    for start in range(0, max_results, page_size):
        params = {
            "search_query": query,
            "start": str(start),
            "max_results": str(min(page_size, max_results - start)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        api_url = api_url or url
        page = fetch_arxiv_page(url, keywords)
        for paper in page:
            papers_by_id[paper["id"]] = paper
        if len(page) < page_size:
            break
        time.sleep(ARXIV_PAGE_DELAY_SECONDS)
    papers = list(papers_by_id.values())
    papers.sort(key=lambda item: (item.get("published", ""), item.get("title", "")), reverse=True)
    return papers, query, api_url


def merge_pool(signature, papers, keywords):
    path = pool_cache_path(signature)
    pool = read_json(path, {"version": CACHE_VERSION, "signature": signature, "keywords": keywords, "papers": {}})
    pool.setdefault("papers", {})
    for paper in papers:
        pool["papers"][paper["id"]] = paper
    pool["version"] = CACHE_VERSION
    pool["signature"] = signature
    pool["keywords"] = keywords
    pool["updatedAt"] = utc_now()
    atomic_write_json(path, pool)


def valid_date_cache(payload, date_range):
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != CACHE_VERSION:
        return None
    cached_range = payload.get("submittedDateRange") or {}
    if cached_range.get("startUtc") != date_range["startUtc"] or cached_range.get("endUtc") != date_range["endUtc"]:
        return None
    return payload


def parse_arxiv_timestamp(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def pool_payload_for_date(date_text, keywords, signature, date_range, cache_path, warning=""):
    pool = read_json(pool_cache_path(signature), None)
    if not isinstance(pool, dict):
        return None
    start = parse_iso_datetime(date_range["startUtcIso"])
    end = parse_iso_datetime(date_range["endUtcIso"])
    papers = []
    for paper in (pool.get("papers") or {}).values():
        published = parse_arxiv_timestamp(paper.get("published"))
        if not published or published < start or published > end:
            continue
        papers.append(paper)
    papers.sort(key=lambda item: (item.get("published", ""), item.get("title", "")), reverse=True)
    if not papers:
        return None
    return {
        "version": CACHE_VERSION,
        "date": date_text,
        "keywords": keywords,
        "signature": signature,
        "query": build_arxiv_query(date_text, keywords),
        "submittedDateRange": date_range,
        "fetchedAt": pool.get("updatedAt"),
        "papers": papers,
        "cached": True,
        "cachePath": str(cache_path),
        "warning": warning,
    }


def load_date_payload(date_text, refresh=False):
    settings = load_settings()
    keywords = settings["keywords"]
    signature = keyword_signature(keywords)
    cache_path = date_cache_path(date_text, signature)
    date_range = arxiv_date_range(date_text)
    cached_payload = valid_date_cache(read_json(cache_path, None), date_range) if cache_path.exists() else None
    latest_day = latest_arxiv_date()
    if isinstance(cached_payload, dict) and not refresh:
        cached_payload["cached"] = True
        cached_payload["cachePath"] = str(cache_path)
        cached_payload["latestAvailableDate"] = latest_day.isoformat()
        cached_payload["arxivCooldown"] = read_arxiv_cooldown()
        return cached_payload
    if not refresh:
        pool_payload = pool_payload_for_date(date_text, keywords, signature, date_range, cache_path)
        if pool_payload:
            pool_payload["latestAvailableDate"] = latest_day.isoformat()
            pool_payload["arxivCooldown"] = read_arxiv_cooldown()
            atomic_write_json(cache_path, pool_payload)
            return pool_payload

    cooldown = read_arxiv_cooldown()
    if cooldown:
        warning = cooldown_warning(cooldown)
        if isinstance(cached_payload, dict):
            cached_payload["cached"] = True
            cached_payload["warning"] = warning
            cached_payload["cachePath"] = str(cache_path)
            cached_payload["arxivCooldown"] = cooldown
            return cached_payload
        pool_payload = pool_payload_for_date(date_text, keywords, signature, date_range, cache_path, warning)
        if pool_payload:
            pool_payload["latestAvailableDate"] = latest_day.isoformat()
            pool_payload["arxivCooldown"] = cooldown
            atomic_write_json(cache_path, pool_payload)
            return pool_payload
        return {
            "version": CACHE_VERSION,
            "date": date_text,
            "keywords": keywords,
            "signature": signature,
            "query": build_arxiv_query(date_text, keywords),
            "submittedDateRange": date_range,
            "fetchedAt": None,
            "papers": [],
            "cached": False,
            "warning": warning + " 当前日期没有可用缓存。",
            "cachePath": str(cache_path),
            "latestAvailableDate": latest_day.isoformat(),
            "arxivCooldown": cooldown,
        }
    try:
        papers, query, api_url = fetch_arxiv(date_text, keywords, settings["maxResults"])
        clear_arxiv_cooldown()
        payload = {
            "version": CACHE_VERSION,
            "date": date_text,
            "keywords": keywords,
            "signature": signature,
            "query": query,
            "submittedDateRange": date_range,
            "apiUrl": api_url,
            "fetchedAt": utc_now(),
            "papers": papers,
            "cached": False,
            "cachePath": str(cache_path),
        }
        atomic_write_json(cache_path, payload)
        merge_pool(signature, papers, keywords)
        return payload
    except ArxivRateLimitError as exc:
        cooldown = write_arxiv_cooldown(str(exc), exc.cooldown_seconds)
        warning = cooldown_warning(cooldown)
        if isinstance(cached_payload, dict):
            cached_payload["cached"] = True
            cached_payload["warning"] = warning
            cached_payload["cachePath"] = str(cache_path)
            cached_payload["arxivCooldown"] = cooldown
            return cached_payload
        pool_payload = pool_payload_for_date(date_text, keywords, signature, date_range, cache_path, warning)
        if pool_payload:
            pool_payload["latestAvailableDate"] = latest_day.isoformat()
            pool_payload["arxivCooldown"] = cooldown
            atomic_write_json(cache_path, pool_payload)
            return pool_payload
        return {
            "version": CACHE_VERSION,
            "date": date_text,
            "keywords": keywords,
            "signature": signature,
            "query": build_arxiv_query(date_text, keywords),
            "submittedDateRange": date_range,
            "fetchedAt": None,
            "papers": [],
            "cached": False,
            "warning": warning + " 当前日期没有可用缓存。",
            "cachePath": str(cache_path),
            "latestAvailableDate": latest_day.isoformat(),
            "arxivCooldown": cooldown,
        }
    except Exception as exc:
        if isinstance(cached_payload, dict):
            cached_payload["cached"] = True
            cached_payload["warning"] = "arXiv 刷新失败，已使用本地缓存：%s" % exc
            cached_payload["cachePath"] = str(cache_path)
            cached_payload["arxivCooldown"] = read_arxiv_cooldown()
            return cached_payload
        pool_payload = pool_payload_for_date(
            date_text,
            keywords,
            signature,
            date_range,
            cache_path,
            "arXiv 刷新失败，已从本地 arXiv 池筛选：%s" % exc,
        )
        if pool_payload:
            pool_payload["latestAvailableDate"] = latest_day.isoformat()
            pool_payload["arxivCooldown"] = read_arxiv_cooldown()
            atomic_write_json(cache_path, pool_payload)
            return pool_payload
        return {
            "version": CACHE_VERSION,
            "date": date_text,
            "keywords": keywords,
            "signature": signature,
            "query": build_arxiv_query(date_text, keywords),
            "submittedDateRange": date_range,
            "fetchedAt": None,
            "papers": [],
            "cached": False,
            "error": "arXiv 请求失败：%s" % exc,
            "cachePath": str(cache_path),
            "latestAvailableDate": latest_day.isoformat(),
            "arxivCooldown": read_arxiv_cooldown(),
        }


def filter_papers(papers, section):
    if section == "all":
        return list(papers)
    return [paper for paper in papers if section in paper.get("sections", [])]


def section_counts(papers):
    counts = {"all": len(papers)}
    for section in SECTIONS:
        section_id = section["id"]
        if section_id == "all":
            continue
        counts[section_id] = sum(1 for paper in papers if section_id in paper.get("sections", []))
    return counts


def read_summary(path):
    payload = read_json(path, None)
    if isinstance(payload, dict):
        return payload
    return None


def paper_summary_has_translation(summary):
    if not isinstance(summary, dict):
        return False
    body = summary.get("summary")
    return isinstance(body, dict) and bool(str(body.get("abstract_zh") or "").strip())


def section_summary_has_categories(summary):
    if not isinstance(summary, dict):
        return False
    body = summary.get("summary")
    return isinstance(body, dict) and isinstance(body.get("category_summaries"), list)


def read_section_summary(path):
    summary = read_summary(path)
    if section_summary_has_categories(summary):
        return summary
    return None


def classified_papers_for_payload(payload):
    keywords = payload.get("keywords") or load_settings().get("keywords", [])
    rows = []
    for paper in payload.get("papers", []):
        next_paper = dict(paper)
        sections, matched_keywords, score, primary_section, section_scores = classify_paper(next_paper, keywords)
        next_paper["sections"] = sections
        next_paper["primarySection"] = primary_section
        next_paper["sectionScores"] = section_scores
        next_paper["matchedKeywords"] = matched_keywords
        next_paper["relevanceScore"] = score
        rows.append(next_paper)
    return rows


def enrich_papers_response(payload, section):
    all_papers = classified_papers_for_payload(payload)
    papers = filter_papers(all_papers, section)
    signature = payload["signature"]
    date_text = payload["date"]
    library = get_library_entries([paper["id"] for paper in papers])
    paper_summaries = {}
    for paper in papers:
        summary = read_summary(qwen_paper_cache_path(date_text, signature, paper["id"]))
        if summary:
            paper_summaries[paper["id"]] = summary
    return {
        "version": APP_VERSION,
        "date": date_text,
        "section": section,
        "sections": SECTIONS,
        "counts": section_counts(all_papers),
        "keywords": payload.get("keywords", []),
        "signature": signature,
        "query": payload.get("query"),
        "submittedDateRange": payload.get("submittedDateRange"),
        "fetchedAt": payload.get("fetchedAt"),
        "cached": payload.get("cached", False),
        "cachePath": payload.get("cachePath"),
        "warning": payload.get("warning"),
        "error": payload.get("error"),
        "latestAvailableDate": payload.get("latestAvailableDate") or latest_arxiv_date().isoformat(),
        "suggestedDate": payload.get("suggestedDate"),
        "arxivCooldown": payload.get("arxivCooldown") or read_arxiv_cooldown(),
        "papers": papers,
        "library": library,
        "sectionSummary": read_section_summary(qwen_section_cache_path(date_text, signature, section)),
        "paperSummaries": paper_summaries,
    }


DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"


def qwen_chat_url(base_url):
    url = (base_url or DEFAULT_QWEN_BASE_URL).rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    return url


def mask_api_key(api_key):
    if not api_key:
        return ""
    tail = api_key[-4:] if len(api_key) >= 4 else api_key
    return "•••• " + tail


def read_local_qwen_config():
    ensure_dirs()
    payload = read_json(QWEN_CONFIG_PATH, {})
    if not isinstance(payload, dict):
        return {}
    return payload


def write_local_qwen_config(payload):
    ensure_dirs()
    atomic_write_json(QWEN_CONFIG_PATH, payload)


def qwen_config():
    local = read_local_qwen_config()
    env_api_key = (
        os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    api_key = env_api_key or str(local.get("apiKey") or "")
    source = "env" if env_api_key else ("local" if api_key else "none")
    base_url = (
        os.environ.get("QWEN_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or str(local.get("baseUrl") or DEFAULT_QWEN_BASE_URL)
    )
    model = os.environ.get("QWEN_MODEL") or str(local.get("model") or DEFAULT_QWEN_MODEL)
    return {
        "configured": bool(api_key),
        "apiKey": api_key,
        "baseUrl": base_url,
        "model": model,
        "source": source,
        "locked": bool(env_api_key) or bool(local.get("locked") and api_key),
        "editable": not bool(env_api_key),
        "keyPreview": mask_api_key(api_key),
        "updatedAt": local.get("updatedAt"),
    }


def public_qwen_config():
    config = qwen_config()
    return {
        "configured": config["configured"],
        "locked": config["locked"],
        "editable": config["editable"],
        "source": config["source"],
        "model": config["model"],
        "baseUrl": config["baseUrl"],
        "keyPreview": config["keyPreview"],
        "updatedAt": config["updatedAt"],
        "configPath": str(QWEN_CONFIG_PATH),
    }


def test_qwen_credentials(config):
    if not config.get("apiKey"):
        raise RuntimeError("缺少 Qwen API Key")
    body = {
        "model": config.get("model") or DEFAULT_QWEN_MODEL,
        "messages": [
            {"role": "system", "content": "你只用于检测 API 是否可用。"},
            {"role": "user", "content": "请只返回 OK"},
        ],
        "temperature": 0,
        "max_tokens": 16,
    }
    request = urllib.request.Request(
        qwen_chat_url(config.get("baseUrl")),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + config["apiKey"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("Qwen 检测失败 HTTP %s：%s" % (exc.code, detail[:300]))
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return clean_text(content) or "OK"


def chat_completion(messages):
    config = qwen_config()
    if not config["apiKey"]:
        raise RuntimeError("未配置 Qwen API Key。请在前台 Qwen 接入面板中检测并锁定 API Key。")
    url = qwen_chat_url(config["baseUrl"])
    body = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + config["apiKey"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("Qwen HTTP %s：%s" % (exc.code, detail[:500]))
    return payload["choices"][0]["message"]["content"]


def parse_jsonish(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"markdown": text, "raw": text}


def paper_brief_for_prompt(paper):
    return {
        "id": paper["id"],
        "title": paper["title"],
        "authors": paper.get("authors", [])[:8],
        "categories": paper.get("categories", []),
        "abstract": paper.get("abstract", "")[:2400],
        "matchedKeywords": paper.get("matchedKeywords", []),
        "sections": paper.get("sections", []),
        "primarySection": paper.get("primarySection", ""),
        "sectionScores": paper.get("sectionScores", {}),
        "absUrl": paper.get("absUrl", ""),
    }


def build_section_summary(date_text, section, signature, papers):
    if not papers:
        return {
            "type": "section",
            "date": date_text,
            "section": section,
            "signature": signature,
            "generatedAt": utc_now(),
            "model": "none",
            "summary": {
                "headline": "选定日期这个子页没有命中论文。",
                "category_summaries": [],
                "key_takeaways": [],
                "papers": [],
                "watchlist": [],
                "markdown": "选定日期这个子页没有命中论文。",
            },
        }
    section_label = next((item["label"] for item in SECTIONS if item["id"] == section), section)
    payload = {
        "date": date_text,
        "section": {"id": section, "label": section_label},
        "category_schema": [
            {"id": item["id"], "label": item["label"], "description": item["description"]}
            for item in SECTIONS
            if item["id"] != "all"
        ],
        "papers": [paper_brief_for_prompt(paper) for paper in papers[:30]],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是具身智能行业的论文雷达编辑，读者关注机器人本体、具身模型、具身数据、具身推理、移动操作、灵巧操作、灵巧手、Ego/UMI 数据采集和真机部署。"
                "请严格输出 JSON，不要输出 markdown 代码围栏。"
                "字段必须包含 headline, category_summaries, key_takeaways, papers, watchlist, markdown。"
                "category_summaries 必须按输入 category_schema 输出，每项包含 id, label, count, summary, highlights, risks。"
                "papers 中每篇包含 id, primary_category, one_liner, value, limitation, tags。"
                "请按具身智能研发决策链路分类总结，而不是泛泛综述；用中文，判断要克制，明确价值、局限和对真机/数据/模型工作的意义。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]
    raw = chat_completion(messages)
    parsed = parse_jsonish(raw)
    return {
        "type": "section",
        "date": date_text,
        "section": section,
        "signature": signature,
        "generatedAt": utc_now(),
        "model": qwen_config()["model"],
        "promptVersion": PROMPT_VERSION,
        "inputPaperIds": [paper["id"] for paper in papers],
        "summary": parsed,
    }


def build_paper_summary(date_text, signature, paper):
    payload = paper_brief_for_prompt(paper)
    messages = [
        {
            "role": "system",
            "content": (
                "你是机器人、具身智能和 VLA 方向的论文阅读助手。"
                "请严格输出 JSON，不要输出 markdown 代码围栏。"
                "字段必须包含 abstract_zh, one_liner, value, limitation, method, should_read, markdown。"
                "abstract_zh 是论文英文摘要的忠实中文翻译，保留模型名、数据集名、指标和公式，不要扩写，不要加入评价。"
                "用中文，一句话摘要要具体，价值和局限要分开。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]
    raw = chat_completion(messages)
    parsed = parse_jsonish(raw)
    return {
        "type": "paper",
        "date": date_text,
        "paperId": paper["id"],
        "signature": signature,
        "generatedAt": utc_now(),
        "model": qwen_config()["model"],
        "promptVersion": PROMPT_VERSION,
        "summary": parsed,
    }


def set_job(job_id, **patch):
    with jobs_lock:
        job = jobs.get(job_id, {})
        job.update(patch)
        jobs[job_id] = job
        return dict(job)


def enqueue_job(kind, cache_path, builder):
    job_id = str(uuid.uuid4())
    now = utc_now()
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "createdAt": now,
            "updatedAt": now,
        }

    def run():
        set_job(job_id, status="running", updatedAt=utc_now())
        try:
            result = builder()
            atomic_write_json(cache_path, result)
            set_job(job_id, status="done", result=result, updatedAt=utc_now())
        except Exception as exc:
            set_job(job_id, status="error", error=str(exc), updatedAt=utc_now())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return jobs[job_id]


def find_paper(payload, paper_id):
    for paper in payload.get("papers", []):
        if paper.get("id") == paper_id or paper.get("versionedId") == paper_id:
            return paper
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalArxivWorkbench/" + APP_VERSION

    def log_message(self, format_text, *args):
        print("[%s] %s" % (self.log_date_time_string(), format_text % args))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/config":
                return self.send_json(HTTPStatus.OK, self.handle_config())
            if path == "/api/papers":
                return self.send_json(HTTPStatus.OK, self.handle_papers(query))
            if path == "/api/library":
                return self.send_json(HTTPStatus.OK, load_library())
            if path == "/api/qwen/config":
                return self.send_json(HTTPStatus.OK, public_qwen_config())
            if path == "/api/qwen/job":
                return self.send_json(HTTPStatus.OK, self.handle_job(query))
            if path == "/" or path == "/index.html":
                return self.send_static(self.frontend_root() / "index.html")
            if path in {"/logo.svg", "/favicon.png", "/apple-touch-icon.png"}:
                return self.send_static(self.frontend_root() / path.lstrip("/"))
            if path == "/favicon.ico":
                return self.send_static(self.frontend_root() / "favicon.png")
            if path.startswith("/assets/"):
                return self.send_static(self.frontend_root() / path.lstrip("/"))
            if path.startswith("/static/"):
                return self.send_static(STATIC_DIR / path[len("/static/") :])
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except ValueError as exc:
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = self.read_body()
            if path == "/api/settings":
                return self.send_json(HTTPStatus.OK, self.handle_settings(body))
            if path == "/api/library":
                return self.send_json(HTTPStatus.OK, self.handle_library_update(body))
            if path == "/api/qwen/config":
                return self.send_json(HTTPStatus.OK, self.handle_qwen_config(body))
            if path == "/api/qwen/unlock":
                return self.send_json(HTTPStatus.OK, self.handle_qwen_unlock())
            if path == "/api/qwen/section":
                return self.send_json(HTTPStatus.OK, self.handle_qwen_section(body))
            if path == "/api/qwen/paper":
                return self.send_json(HTTPStatus.OK, self.handle_qwen_paper(body))
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except ValueError as exc:
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def send_static(self, path):
        try:
            resolved = path.resolve()
            allowed_roots = [STATIC_DIR.resolve()]
            if DIST_DIR.exists():
                allowed_roots.append(DIST_DIR.resolve())
            if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
                return self.send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            raw = resolved.read_bytes()
        except FileNotFoundError:
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        content_type = "text/plain; charset=utf-8"
        if resolved.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif resolved.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif resolved.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif resolved.suffix == ".svg":
            content_type = "image/svg+xml"
        elif resolved.suffix == ".png":
            content_type = "image/png"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def frontend_root(self):
        if (DIST_DIR / "index.html").exists():
            return DIST_DIR
        return STATIC_DIR

    def handle_config(self):
        default_date = latest_arxiv_date().isoformat()
        return {
            "version": APP_VERSION,
            "settings": load_settings(),
            "sections": SECTIONS,
            "qwen": public_qwen_config(),
            "arxiv": {
                "defaultDate": default_date,
                "latestAvailableDate": default_date,
                "cooldown": read_arxiv_cooldown(),
            },
            "paths": {
                "cache": str(CACHE_DIR),
                "library": str(LIBRARY_PATH),
                "settings": str(SETTINGS_PATH),
                "qwen": str(QWEN_CONFIG_PATH),
            },
        }

    def handle_settings(self, body):
        settings = save_settings(body)
        return {"settings": settings, "signature": keyword_signature(settings["keywords"])}

    def handle_papers(self, query):
        date_text = (query.get("date") or [""])[0] or latest_arxiv_date().isoformat()
        parse_date(date_text)
        section = (query.get("section") or ["all"])[0] or "all"
        valid_sections = {item["id"] for item in SECTIONS}
        if section not in valid_sections:
            raise ValueError("未知子页：%s" % section)
        refresh = (query.get("refresh") or ["0"])[0] in {"1", "true", "yes"}
        payload = load_date_payload(date_text, refresh=refresh)
        return enrich_papers_response(payload, section)

    def handle_library_update(self, body):
        paper_id = str(body.get("paperId", "")).strip()
        if not paper_id:
            raise ValueError("缺少 paperId")
        patch = body.get("patch", {})
        if not isinstance(patch, dict):
            raise ValueError("patch 必须是对象")
        return {"paperId": paper_id, "entry": update_library_entry(paper_id, patch)}

    def handle_qwen_config(self, body):
        with qwen_lock:
            current = read_local_qwen_config()
            effective = qwen_config()
            if not effective.get("editable"):
                raise ValueError("当前 Qwen 使用环境变量配置，前台不能覆盖。")

            api_key = str(body.get("apiKey") or "").strip() or str(current.get("apiKey") or "").strip()
            model = clean_text(str(body.get("model") or current.get("model") or DEFAULT_QWEN_MODEL))
            base_url = clean_text(str(body.get("baseUrl") or current.get("baseUrl") or DEFAULT_QWEN_BASE_URL))
            if not api_key:
                raise ValueError("请先输入 Qwen API Key")
            if not model:
                raise ValueError("请填写 Qwen 模型名")
            if not base_url:
                raise ValueError("请填写 Qwen Base URL")

            probe_config = {"apiKey": api_key, "model": model, "baseUrl": base_url}
            probe = test_qwen_credentials(probe_config)
            payload = {
                "apiKey": api_key,
                "model": model,
                "baseUrl": base_url,
                "locked": True,
                "updatedAt": utc_now(),
            }
            write_local_qwen_config(payload)
            return {"ok": True, "probe": probe, "qwen": public_qwen_config()}

    def handle_qwen_unlock(self):
        with qwen_lock:
            effective = qwen_config()
            if not effective.get("editable"):
                raise ValueError("当前 Qwen 使用环境变量配置，前台不能解锁。")
            payload = read_local_qwen_config()
            if payload:
                payload["locked"] = False
                payload["updatedAt"] = utc_now()
                write_local_qwen_config(payload)
            return {"ok": True, "qwen": public_qwen_config()}

    def handle_job(self, query):
        job_id = (query.get("id") or [""])[0]
        with jobs_lock:
            job = jobs.get(job_id)
        if not job:
            raise ValueError("未知任务")
        return job

    def handle_qwen_section(self, body):
        date_text = str(body.get("date", "")).strip()
        section = str(body.get("section", "all")).strip() or "all"
        force = bool(body.get("force"))
        parse_date(date_text)
        valid_sections = {item["id"] for item in SECTIONS}
        if section not in valid_sections:
            raise ValueError("未知子页：%s" % section)
        payload = load_date_payload(date_text, refresh=False)
        signature = payload["signature"]
        cache_path = qwen_section_cache_path(date_text, signature, section)
        if cache_path.exists() and not force:
            summary = read_summary(cache_path)
            if section_summary_has_categories(summary):
                return {"status": "cached", "summary": summary}
        papers = filter_papers(classified_papers_for_payload(payload), section)
        job = enqueue_job(
            "section",
            cache_path,
            lambda: build_section_summary(date_text, section, signature, papers),
        )
        return {"status": job["status"], "job": job}

    def handle_qwen_paper(self, body):
        date_text = str(body.get("date", "")).strip()
        paper_id = str(body.get("paperId", "")).strip()
        force = bool(body.get("force"))
        parse_date(date_text)
        if not paper_id:
            raise ValueError("缺少 paperId")
        payload = load_date_payload(date_text, refresh=False)
        signature = payload["signature"]
        paper = find_paper({"papers": classified_papers_for_payload(payload)}, paper_id)
        if not paper:
            raise ValueError("当天缓存里找不到这篇论文：%s" % paper_id)
        cache_path = qwen_paper_cache_path(date_text, signature, paper["id"])
        if cache_path.exists() and not force:
            summary = read_summary(cache_path)
            if paper_summary_has_translation(summary):
                return {"status": "cached", "summary": summary}
        job = enqueue_job(
            "paper",
            cache_path,
            lambda: build_paper_summary(date_text, signature, paper),
        )
        return {"status": job["status"], "job": job}


def main():
    ensure_dirs()
    load_settings()
    load_library()
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Local arXiv Workbench running at http://127.0.0.1:%s" % port)
    print("Cache: %s" % CACHE_DIR)
    print("Library: %s" % LIBRARY_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
