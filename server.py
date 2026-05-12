#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
DATA_DIR = ROOT / ".data"
LIBRARY_PATH = DATA_DIR / "library.json"

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

CATEGORIES = ("cs.RO", "cs.AI", "cs.CV", "cs.LG", "stat.ML", "eess.SY")
KEYWORDS = (
    "robot",
    "robotics",
    "robotic",
    "embodied",
    "embodiment",
    "manipulation",
    "locomotion",
    "humanoid",
    "quadruped",
    "mobile robot",
    "navigation",
    "slam",
    "grasp",
    "dexterous",
    "teleoperation",
    "sim-to-real",
    "sim2real",
    "vision-language-action",
    "vision language action",
    "vla",
    "diffusion policy",
    "imitation learning",
    "reinforcement learning",
    "tactile",
    "motion planning",
    "trajectory planning",
    "bimanual",
    "legged",
    "hand-eye",
    "real-world robot",
)

USER_CATEGORIES = (
    "未分类",
    "本体/硬件",
    "预训练",
    "后训练",
    "RL/DAgger",
    "具身数据",
    "具身推理",
    "移动操作",
    "灵巧操作",
    "灵巧手",
    "仿真/Sim2Real",
    "评测/Benchmark",
    "待复现",
)
STATUS_OPTIONS = ("unread", "reading", "done", "skip")
ARXIV_POOL_SIZE = 250
DEFAULT_FEED_PAGE_SIZE = 12
LEGACY_CATEGORY_MAP = {
    "VLA/世界模型": "预训练",
    "操作/抓取": "灵巧操作",
    "运动控制": "移动操作",
    "导航/SLAM": "移动操作",
    "仿真/数据": "仿真/Sim2Real",
    "群体/系统": "具身推理",
}

INDUSTRY_SIGNAL_RULES = (
    ("真机", ("real-world", "real robot", "physical robot", "hardware", "onboard", "deployment", "deployed", "field", "in-the-wild"), 3),
    ("开源", ("open-source", "github", "code is available", "code, evaluation", "huggingface", "released at", "project page"), 2),
    ("具身数据", ("dataset", "demonstration", "episodes", "data collection", "teleoperation", "lerobot", "umi", "ego", "open x-embodiment"), 3),
    ("DAgger/RL", ("dagger", "reinforcement learning", "reward", "policy optimization", "online correction"), 3),
    ("移动操作", ("mobile manipulator", "mobile robot", "navigation", "slam", "relocalization", "locomotion", "base-arm", "uav"), 3),
    ("灵巧操作", ("dexterous", "in-hand", "bimanual", "grasp", "manipulation", "contact-rich", "folding", "cloth"), 3),
    ("灵巧手", ("dexterous hand", "multifinger", "multi-finger", "allegro", "shadow hand", "hand-object", "tactile"), 4),
    ("具身模型", ("vision-language-action", "vla", "world action model", "foundation model", "flow matching", "diffusion policy", "policy learning"), 2),
    ("Sim2Real", ("sim-to-real", "sim2real", "real2sim", "simulation", "domain randomization", "isaac", "mujoco", "digital twin"), 2),
    ("评测", ("benchmark", "evaluation", "metric", "suite", "protocol", "baseline", "ood", "generalization"), 2),
)


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    updated: str
    categories: list[str]
    primary_category: str
    arxiv_url: str
    pdf_url: str
    keyword_matches: list[str]
    score: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def request_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int = 90) -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def salvage_arxiv_feed(partial: str) -> str | None:
    if "<feed" not in partial or "<entry>" not in partial:
        return None
    if partial.rstrip().endswith("</feed>"):
        return partial
    entry_end = partial.rfind("</entry>")
    if entry_end < 0:
        return None
    return partial[: entry_end + len("</entry>")] + "\n</feed>"


def request_text(url: str, timeout: int = 30, attempts: int = 3) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "embodied-zhidu/0.2 (+local research assistant)",
        },
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except http.client.IncompleteRead as exc:
            last_error = exc
            partial = exc.partial.decode("utf-8", errors="ignore")
            salvaged = salvage_arxiv_feed(partial)
            if salvaged:
                return salvaged
            time.sleep(0.5 + attempt)
        except (http.client.RemoteDisconnected, ConnectionResetError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.5 + attempt)
    if last_error:
        raise last_error
    raise RuntimeError("请求失败")


def cache_get(name: str, max_age_seconds: int) -> Any | None:
    path = CACHE_DIR / name
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_set(name: str, payload: Any) -> None:
    path = CACHE_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_library() -> dict[str, Any]:
    return {"papers": {}}


def load_library() -> dict[str, Any]:
    if not LIBRARY_PATH.exists():
        return default_library()
    try:
        payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_library()
    if not isinstance(payload, dict):
        return default_library()
    papers = payload.get("papers")
    if not isinstance(papers, dict):
        payload["papers"] = {}
    return payload


def save_library(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    temp_path = LIBRARY_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(LIBRARY_PATH)


def clean_note(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:2000]


def normalize_status(value: Any) -> str:
    return value if value in STATUS_OPTIONS else "unread"


def normalize_user_category(value: Any) -> str:
    value = LEGACY_CATEGORY_MAP.get(value, value)
    return value if value in USER_CATEGORIES else "未分类"


def normalize_library_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    entry = entry or {}
    return {
        "favorite": bool(entry.get("favorite", False)),
        "user_category": normalize_user_category(entry.get("user_category")),
        "status": normalize_status(entry.get("status")),
        "notes": clean_note(entry.get("notes", "")),
        "updated_at": entry.get("updated_at", ""),
    }


def is_neutral_library_entry(entry: dict[str, Any]) -> bool:
    return (
        not entry.get("favorite")
        and entry.get("user_category") == "未分类"
        and entry.get("status") == "unread"
        and not entry.get("notes")
    )


def update_library_entry(paper_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    library = load_library()
    papers = library.setdefault("papers", {})
    current = normalize_library_entry(papers.get(paper_id) if isinstance(papers.get(paper_id), dict) else None)

    if "favorite" in changes:
        current["favorite"] = bool(changes["favorite"])
    if "user_category" in changes:
        current["user_category"] = normalize_user_category(changes["user_category"])
    if "status" in changes:
        current["status"] = normalize_status(changes["status"])
    if "notes" in changes:
        current["notes"] = clean_note(changes["notes"])

    current["updated_at"] = utc_now().isoformat()
    if is_neutral_library_entry(current):
        papers.pop(paper_id, None)
    else:
        papers[paper_id] = current
    save_library(library)
    return current


def library_stats(library: dict[str, Any]) -> dict[str, Any]:
    papers = library.get("papers", {})
    if not isinstance(papers, dict):
        papers = {}
    normalized = [
        normalize_library_entry(entry)
        for entry in papers.values()
        if isinstance(entry, dict)
    ]
    by_category = {category: 0 for category in USER_CATEGORIES}
    by_status = {status: 0 for status in STATUS_OPTIONS}
    for entry in normalized:
        by_category[entry["user_category"]] += 1
        by_status[entry["status"]] += 1
    return {
        "tracked": len(normalized),
        "favorites": sum(1 for entry in normalized if entry["favorite"]),
        "notes": sum(1 for entry in normalized if entry["notes"]),
        "by_category": by_category,
        "by_status": by_status,
    }


def attach_library_state(papers: list[dict[str, Any]], library: dict[str, Any]) -> list[dict[str, Any]]:
    states = library.get("papers", {})
    if not isinstance(states, dict):
        states = {}
    enriched = []
    for paper in papers:
        state = normalize_library_entry(states.get(paper["id"]) if isinstance(states.get(paper["id"]), dict) else None)
        item = dict(paper)
        item.update(state)
        enriched.append(item)
    return enriched


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_arxiv_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def arxiv_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def paper_from_entry(entry: ET.Element) -> Paper | None:
    title = normalize_space(entry.findtext("atom:title", default="", namespaces=ARXIV_NAMESPACES))
    abstract = normalize_space(entry.findtext("atom:summary", default="", namespaces=ARXIV_NAMESPACES))
    link = normalize_space(entry.findtext("atom:id", default="", namespaces=ARXIV_NAMESPACES))
    published = normalize_space(entry.findtext("atom:published", default="", namespaces=ARXIV_NAMESPACES))
    updated = normalize_space(entry.findtext("atom:updated", default="", namespaces=ARXIV_NAMESPACES))
    if not title or not link or not published:
        return None

    authors = [
        normalize_space(author.findtext("atom:name", default="", namespaces=ARXIV_NAMESPACES))
        for author in entry.findall("atom:author", ARXIV_NAMESPACES)
    ]
    authors = [author for author in authors if author]

    categories = [
        node.attrib.get("term", "")
        for node in entry.findall("atom:category", ARXIV_NAMESPACES)
        if node.attrib.get("term")
    ]
    primary = entry.find("arxiv:primary_category", ARXIV_NAMESPACES)
    primary_category = primary.attrib.get("term", categories[0] if categories else "")

    pdf_url = ""
    for link_node in entry.findall("atom:link", ARXIV_NAMESPACES):
        if link_node.attrib.get("title") == "pdf":
            pdf_url = link_node.attrib.get("href", "")
            break
    if not pdf_url and link:
        pdf_url = link.replace("/abs/", "/pdf/") + ".pdf"

    haystack = f"{title} {abstract}".lower()
    matches = sorted({keyword for keyword in KEYWORDS if keyword in haystack})
    is_robotics_category = primary_category == "cs.RO" or "cs.RO" in categories
    if not matches and not is_robotics_category:
        return None

    score = len(matches) + (4 if is_robotics_category else 0)
    if any(term in haystack for term in ("humanoid", "manipulation", "embodied", "vla")):
        score += 2

    return Paper(
        id=arxiv_id_from_url(link),
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        updated=updated,
        categories=categories,
        primary_category=primary_category,
        arxiv_url=link,
        pdf_url=pdf_url,
        keyword_matches=matches,
        score=score,
    )


def fetch_category(category: str, max_results: int, refresh: bool) -> list[dict[str, Any]]:
    cache_name = f"arxiv_{category}_{max_results}.json"
    if not refresh:
        cached = cache_get(cache_name, max_age_seconds=60 * 45)
        if cached is not None:
            return cached

    query = urllib.parse.urlencode(
        {
            "search_query": f"cat:{category}",
            "start": "0",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    xml_text = request_text(f"{ARXIV_API}?{query}")
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ARXIV_NAMESPACES):
        paper = paper_from_entry(entry)
        if paper:
            papers.append(asdict(paper))
    cache_set(cache_name, papers)
    return papers


def fetch_arxiv_pool(max_results: int, refresh: bool) -> list[dict[str, Any]]:
    cache_name = f"arxiv_pool_{max_results}.json"
    if not refresh:
        cached = cache_get(cache_name, max_age_seconds=60 * 45)
        if cached is not None:
            return cached

    search_query = "(" + " OR ".join(f"cat:{category}" for category in CATEGORIES) + ")"
    query = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": "0",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    xml_text = request_text(f"{ARXIV_API}?{query}")
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ARXIV_NAMESPACES):
        paper = paper_from_entry(entry)
        if paper:
            papers.append(asdict(paper))
    cache_set(cache_name, papers)
    return papers


def fetch_recent_papers(days: int, refresh: bool = False, max_results: int = ARXIV_POOL_SIZE) -> list[dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=days)
    max_results = max(80, min(ARXIV_POOL_SIZE, max_results))
    by_id: dict[str, dict[str, Any]] = {}

    try:
        papers = fetch_arxiv_pool(max_results, refresh)
    except (
        urllib.error.URLError,
        TimeoutError,
        ET.ParseError,
        http.client.IncompleteRead,
        http.client.RemoteDisconnected,
        ConnectionResetError,
    ) as exc:
        raise RuntimeError(f"arXiv 抓取失败：{exc}") from exc

    for paper in papers:
        try:
            published_at = parse_arxiv_datetime(paper["published"])
        except ValueError:
            continue
        if published_at < cutoff:
            continue
        existing = by_id.get(paper["id"])
        if not existing or paper["score"] > existing["score"]:
            by_id[paper["id"]] = paper

    sorted_papers = sorted(
        by_id.values(),
        key=lambda item: (item["score"], item["published"]),
        reverse=True,
    )
    return sorted_papers


def qwen_config() -> dict[str, Any]:
    key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    model = os.getenv("QWEN_MODEL", "qwen3.6-max-preview")
    fallback_models = [
        item.strip()
        for item in os.getenv("QWEN_FALLBACK_MODELS", "qwen3-max,qwen3-max-2026-01-23").split(",")
        if item.strip()
    ]
    return {
        "api_key": key,
        "model": model,
        "fallback_models": [item for item in fallback_models if item != model],
        "enable_thinking": os.getenv("QWEN_ENABLE_THINKING", "1") != "0",
        "thinking_budget": parse_int(os.getenv("QWEN_THINKING_BUDGET"), 4096, 512, 32768),
        "url": os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
    }


def qwen_cache_key(papers: list[dict[str, Any]], model: str, enable_thinking: bool = False) -> str:
    seed = json.dumps(
        {
            "model": model,
            "enable_thinking": enable_thinking,
            "papers": [
                {
                    "id": paper["id"],
                    "updated": paper["updated"],
                    "title": paper["title"],
                }
                for paper in papers
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "qwen_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24] + ".json"


def qwen_models_to_try(config: dict[str, Any]) -> list[str]:
    models = [config["model"], *config.get("fallback_models", [])]
    unique_models = []
    for model in models:
        if model and model not in unique_models:
            unique_models.append(model)
    return unique_models


def qwen_attempts(config: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = []
    for model in qwen_models_to_try(config):
        thinking_modes = [False]
        if config["enable_thinking"]:
            thinking_modes = [True, False]
        for enable_thinking in thinking_modes:
            attempts.append({"model": model, "enable_thinking": enable_thinking})
    return attempts


def build_qwen_prompt(papers: list[dict[str, Any]]) -> str:
    compact = []
    for paper in papers:
        compact.append(
            {
                "id": paper["id"],
                "title": paper["title"],
                "authors": paper["authors"][:8],
                "published": paper["published"],
                "categories": paper["categories"],
                "keywords": paper["keyword_matches"],
                "abstract": paper["abstract"][:1600],
            }
        )
    return (
        "请阅读下面 arXiv 论文元数据，筛选机器人、具身智能、VLA、操作、导航、"
        "运动控制、仿真到现实等方向的论文。用中文输出 JSON，不要 Markdown。"
        "JSON 结构必须是："
        "{\"daily_brief\":\"不超过180字的总览\","
        "\"themes\":[\"主题1\",\"主题2\",\"主题3\"],"
        "\"papers\":[{\"id\":\"arxiv id\",\"one_line\":\"一句话结论\","
        "\"why_it_matters\":\"为什么值得读\","
        "\"methods\":[\"方法点1\",\"方法点2\"],"
        "\"limitations\":\"局限或待读点\","
        "\"read_priority\":\"high|medium|low\"}]}。"
        "优先指出工程可用性、机器人系统价值和与具身智能的关系。\n\n"
        + json.dumps(compact, ensure_ascii=False)
    )


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def summarize_with_qwen(papers: list[dict[str, Any]], refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    config = qwen_config()
    meta = {
        "enabled": bool(config["api_key"]),
        "used": False,
        "model": config["model"],
        "attempted_models": [],
        "enable_thinking": config["enable_thinking"],
        "error": None,
    }
    if not papers:
        return {"daily_brief": "今天没有匹配到新的机器人或具身智能论文。", "themes": [], "papers": []}, meta
    if not config["api_key"]:
        return fallback_summary(papers), meta

    cache_name = qwen_cache_key(papers, config["model"], config["enable_thinking"])
    if not refresh:
        cached = cache_get(cache_name, max_age_seconds=60 * 60 * 12)
        if cached is not None:
            meta["used"] = True
            meta["cached"] = True
            return cached, meta

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    messages = [
        {
            "role": "system",
            "content": "你是机器人和具身智能方向的研究助理，擅长从论文摘要中提炼技术路线、价值和阅读优先级。",
        },
        {"role": "user", "content": build_qwen_prompt(papers)},
    ]

    for attempt in qwen_attempts(config):
        model = attempt["model"]
        enable_thinking = attempt["enable_thinking"]
        meta["attempted_models"].append(
            f"{model}{' + thinking' if enable_thinking else ''}"
        )
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if enable_thinking:
            body["enable_thinking"] = True
            body["thinking_budget"] = config["thinking_budget"]
        try:
            data = request_json(config["url"], body, headers)
            content = data["choices"][0]["message"]["content"]
            summary = extract_json_object(content)
            cache_set(qwen_cache_key(papers, model, enable_thinking), summary)
            meta["used"] = True
            meta["cached"] = False
            meta["model"] = model
            meta["enable_thinking"] = enable_thinking
            return summary, meta
        except (
            KeyError,
            json.JSONDecodeError,
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as exc:
            meta["error"] = str(exc)

    return fallback_summary(papers), meta


def fallback_summary(papers: list[dict[str, Any]]) -> dict[str, Any]:
    themes = []
    theme_rules = (
        ("机器人操作", ("manipulation", "grasp", "dexterous", "bimanual")),
        ("具身智能/VLA", ("embodied", "vision-language-action", "vision language action", "vla")),
        ("运动与导航", ("locomotion", "navigation", "slam", "motion planning", "trajectory")),
        ("学习策略", ("diffusion policy", "imitation learning", "reinforcement learning")),
        ("Sim-to-real", ("sim-to-real", "sim2real", "real-world robot")),
    )
    haystack = " ".join(f"{paper['title']} {paper['abstract']}".lower() for paper in papers)
    for label, terms in theme_rules:
        if any(term in haystack for term in terms):
            themes.append(label)
    if not themes:
        themes = ["机器人", "具身智能", "机器学习"]

    paper_summaries = []
    for paper in papers:
        abstract = paper["abstract"]
        first_sentence = re.split(r"(?<=[.!?])\s+", abstract)[0] if abstract else paper["title"]
        priority = "high" if paper["score"] >= 7 else "medium" if paper["score"] >= 4 else "low"
        paper_summaries.append(
            {
                "id": paper["id"],
                "one_line": first_sentence[:220],
                "why_it_matters": "根据标题、摘要和关键词命中判断，这篇论文与机器人或具身智能方向相关。",
                "methods": paper["keyword_matches"][:4] or paper["categories"][:3],
                "limitations": "未调用 Qwen，仅基于摘要做规则提取；建议打开原文确认实验设置和结果。",
                "read_priority": priority,
            }
        )

    return {
        "daily_brief": f"匹配到 {len(papers)} 篇近期机器人/具身智能相关论文。当前为本地规则摘要；配置 Qwen API key 后会生成更完整的中文梳理。",
        "themes": themes[:5],
        "papers": paper_summaries,
    }


def derive_industry_signals(paper: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [
            paper.get("title", ""),
            paper.get("abstract", ""),
            " ".join(paper.get("categories", [])),
            " ".join(paper.get("keyword_matches", [])),
            paper.get("one_line", ""),
            paper.get("why_it_matters", ""),
        ]
    ).lower()

    signals = []
    score = 0
    for label, terms, weight in INDUSTRY_SIGNAL_RULES:
        if any(term in text for term in terms):
            signals.append(label)
            score += weight

    if paper.get("read_priority") == "high":
        score += 2
    if paper.get("score", 0) >= 8:
        score += 1

    if score >= 11:
        level = "core"
        label = "核心关注"
    elif score >= 7:
        level = "watch"
        label = "重点跟踪"
    elif score >= 4:
        level = "scan"
        label = "快速扫读"
    else:
        level = "archive"
        label = "归档备查"

    return {
        "industry_signals": signals[:6],
        "industry_score": score,
        "industry_level": level,
        "industry_label": label,
    }


def rank_feed_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        papers,
        key=lambda paper: (
            derive_industry_signals(paper)["industry_score"],
            paper.get("score", 0),
            paper.get("published", ""),
        ),
        reverse=True,
    )


def merge_summaries(papers: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {item.get("id"): item for item in summary.get("papers", []) if isinstance(item, dict)}
    fallback_by_id = {
        item.get("id"): item
        for item in fallback_summary(papers).get("papers", [])
        if isinstance(item, dict)
    }
    merged = []
    for paper in papers:
        item = dict(paper)
        fallback = fallback_by_id.get(paper["id"], {})
        ai = by_id.get(paper["id"], {})
        item.update(
            {
                "one_line": ai.get("one_line") or fallback.get("one_line", ""),
                "why_it_matters": ai.get("why_it_matters") or fallback.get("why_it_matters", ""),
                "methods": ai.get("methods") or fallback.get("methods", []),
                "limitations": ai.get("limitations") or fallback.get("limitations", ""),
                "read_priority": ai.get("read_priority") or fallback.get("read_priority", "medium"),
            }
        )
        item.update(derive_industry_signals(item))
        merged.append(item)
    return merged


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "EmbodiedPaperDesk/0.2"

    def translate_path(self, path: str) -> str:
        parsed = urllib.parse.urlparse(path)
        clean_path = parsed.path
        if clean_path == "/":
            return str(STATIC_DIR / "index.html")
        return str(STATIC_DIR / clean_path.lstrip("/"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "has_qwen_key": bool(qwen_config()["api_key"]),
                    "qwen_model": qwen_config()["model"],
                    "time": utc_now().isoformat(),
                }
            )
            return
        if parsed.path == "/api/settings":
            self.send_json(
                {
                    "categories": CATEGORIES,
                    "keywords": KEYWORDS,
                    "user_categories": USER_CATEGORIES,
                    "status_options": STATUS_OPTIONS,
                    "qwen_model": qwen_config()["model"],
                    "has_qwen_key": bool(qwen_config()["api_key"]),
                }
            )
            return
        if parsed.path == "/api/library":
            library = load_library()
            self.send_json(
                {
                    "papers": library.get("papers", {}),
                    "stats": library_stats(library),
                    "user_categories": USER_CATEGORIES,
                    "status_options": STATUS_OPTIONS,
                }
            )
            return
        if parsed.path == "/api/papers":
            self.handle_papers(parsed)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/library/paper":
            self.handle_library_update()
            return
        self.send_json({"error": "未知接口"}, status=HTTPStatus.NOT_FOUND)

    def handle_papers(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        days = parse_int(first(params, "days"), default=3, minimum=1, maximum=14)
        offset = parse_int(first(params, "offset"), default=0, minimum=0, maximum=1000)
        page_size = parse_int(
            first(params, "page_size") or first(params, "limit"),
            default=DEFAULT_FEED_PAGE_SIZE,
            minimum=6,
            maximum=24,
        )
        refresh = first(params, "refresh") == "1"
        want_qwen = first(params, "qwen", "1") != "0"

        try:
            all_papers = rank_feed_papers(fetch_recent_papers(days=days, refresh=refresh))
            total = len(all_papers)
            papers = all_papers[offset : offset + page_size]
            next_offset = offset + len(papers)
            has_more = next_offset < total
            if want_qwen:
                summary, qwen_meta = summarize_with_qwen(papers, refresh=refresh)
            else:
                summary, qwen_meta = fallback_summary(papers), {
                    "enabled": bool(qwen_config()["api_key"]),
                    "used": False,
                    "model": qwen_config()["model"],
                    "error": None,
                }
            library = load_library()
            merged = attach_library_state(merge_summaries(papers, summary), library)
            self.send_json(
                {
                    "generated_at": utc_now().isoformat(),
                    "source": "arXiv",
                    "filters": {"days": days, "offset": offset, "page_size": page_size, "categories": CATEGORIES},
                    "pagination": {
                        "offset": offset,
                        "page_size": page_size,
                        "returned": len(papers),
                        "total": total,
                        "next_offset": next_offset,
                        "has_more": has_more,
                    },
                    "qwen": qwen_meta,
                    "library": library_stats(library),
                    "daily_brief": summary.get("daily_brief", ""),
                    "themes": summary.get("themes", []),
                    "papers": merged,
                }
            )
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.send_json({"error": f"服务处理失败：{exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self, max_bytes: int = 64 * 1024) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size <= 0:
            return {}
        if size > max_bytes:
            raise ValueError("请求体过大")
        raw = self.rfile.read(size).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON object")
        return data

    def handle_library_update(self) -> None:
        try:
            payload = self.read_json_body()
            paper_id = normalize_space(str(payload.get("id", "")))
            if not paper_id:
                self.send_json({"error": "缺少论文 id"}, status=HTTPStatus.BAD_REQUEST)
                return
            state = update_library_entry(paper_id, payload)
            self.send_json({"id": paper_id, "state": state, "library": library_stats(load_library())})
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def first(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = params.get(key)
    if not values:
        return default
    return values[0]


def main() -> None:
    port = int(os.getenv("PORT", "8787"))
    address = os.getenv("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((address, port), AppHandler)
    print(f"Serving 具身智读 at http://{address}:{port}")
    print("Set DASHSCOPE_API_KEY or QWEN_API_KEY to enable Qwen summaries.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
