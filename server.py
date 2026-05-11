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
            "User-Agent": "qwen-embodied-paper-radar/0.1 (+local research assistant)",
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


def fetch_recent_papers(days: int, limit: int, refresh: bool = False) -> list[dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=days)
    max_results = max(80, min(250, limit * 12))
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
    return sorted_papers[:limit]


def qwen_config() -> dict[str, Any]:
    key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    model = os.getenv("QWEN_MODEL", "qwen3.6-max-preview")
    fallback_models = [
        item.strip()
        for item in os.getenv("QWEN_FALLBACK_MODELS", "qwen3-max,qwen-max-latest").split(",")
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
        merged.append(item)
    return merged


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "QwenPaperRadar/0.1"

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
                    "qwen_model": qwen_config()["model"],
                    "has_qwen_key": bool(qwen_config()["api_key"]),
                }
            )
            return
        if parsed.path == "/api/papers":
            self.handle_papers(parsed)
            return
        super().do_GET()

    def handle_papers(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        days = parse_int(first(params, "days"), default=2, minimum=1, maximum=14)
        limit = parse_int(first(params, "limit"), default=18, minimum=3, maximum=50)
        refresh = first(params, "refresh") == "1"
        want_qwen = first(params, "qwen", "1") != "0"

        try:
            papers = fetch_recent_papers(days=days, limit=limit, refresh=refresh)
            if want_qwen:
                summary, qwen_meta = summarize_with_qwen(papers, refresh=refresh)
            else:
                summary, qwen_meta = fallback_summary(papers), {
                    "enabled": bool(qwen_config()["api_key"]),
                    "used": False,
                    "model": qwen_config()["model"],
                    "error": None,
                }
            self.send_json(
                {
                    "generated_at": utc_now().isoformat(),
                    "source": "arXiv",
                    "filters": {"days": days, "limit": limit, "categories": CATEGORIES},
                    "qwen": qwen_meta,
                    "daily_brief": summary.get("daily_brief", ""),
                    "themes": summary.get("themes", []),
                    "papers": merge_summaries(papers, summary),
                }
            )
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.send_json({"error": f"服务处理失败：{exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

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
    print(f"Serving Qwen Paper Radar at http://{address}:{port}")
    print("Set DASHSCOPE_API_KEY or QWEN_API_KEY to enable Qwen summaries.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
