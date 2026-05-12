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
ENV_PATH = ROOT / ".env"


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
TRAILING_URL_CHARS = ".,;:!?)]}'\""
DATASET_DOMAINS = (
    "huggingface.co/datasets",
    "zenodo.org",
    "figshare.com",
    "kaggle.com",
    "dataverse",
    "osf.io",
)
PROJECT_DOMAINS = (
    "github.io",
    "sites.google.com",
    "pages.dev",
    "vercel.app",
    "netlify.app",
    "notion.site",
)
AFFILIATION_DOMAIN_MAP = {
    "mit.edu": "MIT",
    "stanford.edu": "Stanford University",
    "berkeley.edu": "UC Berkeley",
    "cmu.edu": "Carnegie Mellon University",
    "gatech.edu": "Georgia Tech",
    "princeton.edu": "Princeton University",
    "harvard.edu": "Harvard University",
    "columbia.edu": "Columbia University",
    "cornell.edu": "Cornell University",
    "ucla.edu": "UCLA",
    "ucsd.edu": "UC San Diego",
    "washington.edu": "University of Washington",
    "umich.edu": "University of Michigan",
    "ethz.ch": "ETH Zurich",
    "epfl.ch": "EPFL",
    "ox.ac.uk": "University of Oxford",
    "cam.ac.uk": "University of Cambridge",
    "imperial.ac.uk": "Imperial College London",
    "nus.edu.sg": "National University of Singapore",
    "ntu.edu.sg": "Nanyang Technological University",
    "tsinghua.edu.cn": "Tsinghua University",
    "pku.edu.cn": "Peking University",
    "sjtu.edu.cn": "Shanghai Jiao Tong University",
    "zju.edu.cn": "Zhejiang University",
    "ustc.edu.cn": "University of Science and Technology of China",
    "nvidia.com": "NVIDIA",
    "research.google": "Google Research",
    "deepmind.google": "Google DeepMind",
    "microsoft.com": "Microsoft",
    "meta.com": "Meta",
    "apple.com": "Apple",
    "amazon.science": "Amazon",
}
KNOWN_AFFILIATIONS = (
    "Carnegie Mellon University",
    "Stanford University",
    "UC Berkeley",
    "University of California, Berkeley",
    "Massachusetts Institute of Technology",
    "MIT",
    "ETH Zurich",
    "EPFL",
    "Tsinghua University",
    "Peking University",
    "Shanghai Jiao Tong University",
    "Zhejiang University",
    "University of Science and Technology of China",
    "National University of Singapore",
    "Nanyang Technological University",
    "University of Oxford",
    "University of Cambridge",
    "Imperial College London",
    "University of Washington",
    "University of Michigan",
    "Georgia Tech",
    "Google DeepMind",
    "Google Research",
    "Microsoft Research",
    "NVIDIA",
    "Meta AI",
    "Amazon",
    "OpenAI",
)

GITHUB_OWNER_AFFILIATIONS = {
    "google-research": "Google Research",
    "deepmind": "Google DeepMind",
    "facebookresearch": "Meta AI",
    "meta-llama": "Meta AI",
    "microsoft": "Microsoft",
    "microsoftresearch": "Microsoft Research",
    "nvlabs": "NVIDIA",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "stanfordvl": "Stanford University",
    "stanford-iliad": "Stanford University",
    "stanfordasl": "Stanford University",
    "berkeleyautomation": "UC Berkeley",
    "cmu-roboarch": "Carnegie Mellon University",
    "mit-han-lab": "MIT",
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
DEFAULT_FEED_PAGE_SIZE = 5
FEED_CACHE_SECONDS = 60 * 45
FEED_WINDOWS = (1, 3, 7)
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
    comment: str
    doi: str
    external_links: list[dict[str, str]]
    affiliations: list[str]
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


def clean_url(value: str) -> str:
    return normalize_space(value).rstrip(TRAILING_URL_CHARS)


def domain_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return ""
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def path_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).path or ""
    except ValueError:
        return ""


def same_domain(domain: str, suffix: str) -> bool:
    return domain == suffix or domain.endswith("." + suffix)


def context_for_url(text: str, url: str, window: int = 72) -> str:
    lower_text = text.lower()
    lower_url = url.lower()
    index = lower_text.find(lower_url)
    if index < 0:
        return ""
    start = max(0, index - window)
    end = min(len(text), index + len(url) + window)
    return lower_text[start:end]


def external_link_kind(url: str, context: str = "") -> tuple[str, str]:
    domain = domain_from_url(url)
    lower_url = url.lower()
    lower_context = context.lower()
    path = path_from_url(url).lower()

    if same_domain(domain, "github.com"):
        return "github", "GitHub"
    if same_domain(domain, "gitlab.com"):
        return "code", "代码"
    if same_domain(domain, "huggingface.co"):
        if path.startswith("/datasets/") or "dataset" in lower_context or "benchmark" in lower_context:
            return "dataset", "数据"
        if path.startswith("/spaces/"):
            return "project", "项目"
        return "huggingface", "HuggingFace"
    if same_domain(domain, "doi.org"):
        return "doi", "DOI"
    if any(marker in lower_url for marker in DATASET_DOMAINS) or any(
        token in lower_context for token in ("dataset", "benchmark", "data release")
    ):
        return "dataset", "数据"
    if any(same_domain(domain, marker) for marker in PROJECT_DOMAINS) or any(
        token in lower_context for token in ("project page", "project website", "homepage", "webpage", "website")
    ):
        return "project", "项目"
    if any(token in lower_context for token in ("code", "repository", "repo", "implementation")):
        return "code", "代码"
    return "website", "网站"


def is_internal_paper_url(url: str) -> bool:
    domain = domain_from_url(url)
    return same_domain(domain, "arxiv.org") or same_domain(domain, "export.arxiv.org")


def append_unique(values: list[str], value: str, limit: int | None = None) -> None:
    clean_value = normalize_space(value).strip(" ,;:()[]{}")
    if not clean_value:
        return
    existing = {item.casefold() for item in values}
    if clean_value.casefold() in existing:
        return
    if limit is not None and len(values) >= limit:
        return
    values.append(clean_value)


def extract_external_links(texts: list[str], entry_urls: list[str] | None = None, doi: str = "") -> list[dict[str, str]]:
    candidates: list[tuple[str, str]] = []
    for text in texts:
        if not text:
            continue
        for match in URL_RE.finditer(text):
            url = clean_url(match.group(0))
            if url:
                candidates.append((url, context_for_url(text, url)))
    for url in entry_urls or []:
        clean = clean_url(url)
        if clean:
            candidates.append((clean, ""))
    if doi:
        doi_url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
        candidates.append((clean_url(doi_url), ""))

    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for url, context in candidates:
        if not url.startswith(("http://", "https://")):
            continue
        if is_internal_paper_url(url):
            continue
        domain = domain_from_url(url)
        if not domain:
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        kind, label = external_link_kind(url, context)
        links.append({"kind": kind, "label": label, "url": url, "domain": domain})
        seen.add(key)
        if len(links) >= 8:
            break
    return links


def github_owner_from_url(url: str) -> str:
    if not same_domain(domain_from_url(url), "github.com"):
        return ""
    parts = [part for part in path_from_url(url).split("/") if part]
    return parts[0].lower() if parts else ""


def affiliation_from_link(url: str) -> str:
    domain = domain_from_url(url)
    if not domain:
        return ""

    owner = github_owner_from_url(url)
    if owner and owner in GITHUB_OWNER_AFFILIATIONS:
        return GITHUB_OWNER_AFFILIATIONS[owner]

    for suffix, affiliation in AFFILIATION_DOMAIN_MAP.items():
        if same_domain(domain, suffix):
            return affiliation
    return ""


def extract_affiliations(texts: list[str], links: list[dict[str, str]] | None = None) -> list[str]:
    combined = " ".join(text for text in texts if text)
    affiliations: list[str] = []

    for affiliation in KNOWN_AFFILIATIONS:
        if re.search(rf"\b{re.escape(affiliation)}\b", combined, re.IGNORECASE):
            append_unique(affiliations, affiliation, limit=6)

    patterns = (
        r"\b(?:University|Institute|School|College) of [A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5}\b",
        r"\b[A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5}\s+(?:University|Institute|Laboratory|Lab|College|School)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, combined):
            append_unique(affiliations, match.group(0), limit=6)

    for link in links or []:
        if not isinstance(link, dict):
            continue
        affiliation = affiliation_from_link(link.get("url", ""))
        append_unique(affiliations, affiliation, limit=6)
    return affiliations[:6]


def enrich_paper_metadata(paper: dict[str, Any]) -> dict[str, Any]:
    item = dict(paper)
    item.setdefault("comment", "")
    item.setdefault("doi", "")
    texts = [item.get("title", ""), item.get("abstract", ""), item.get("comment", "")]
    if not isinstance(item.get("external_links"), list) or not item.get("external_links"):
        item["external_links"] = extract_external_links(texts, [item.get("arxiv_url", ""), item.get("pdf_url", "")], item.get("doi", ""))
    if not isinstance(item.get("affiliations"), list) or not item.get("affiliations"):
        item["affiliations"] = extract_affiliations(texts, item.get("external_links", []))
    return item


def paper_from_entry(entry: ET.Element) -> Paper | None:
    title = normalize_space(entry.findtext("atom:title", default="", namespaces=ARXIV_NAMESPACES))
    abstract = normalize_space(entry.findtext("atom:summary", default="", namespaces=ARXIV_NAMESPACES))
    link = normalize_space(entry.findtext("atom:id", default="", namespaces=ARXIV_NAMESPACES))
    published = normalize_space(entry.findtext("atom:published", default="", namespaces=ARXIV_NAMESPACES))
    updated = normalize_space(entry.findtext("atom:updated", default="", namespaces=ARXIV_NAMESPACES))
    comment = normalize_space(entry.findtext("arxiv:comment", default="", namespaces=ARXIV_NAMESPACES))
    doi = normalize_space(entry.findtext("arxiv:doi", default="", namespaces=ARXIV_NAMESPACES))
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
    entry_urls = [link]
    for link_node in entry.findall("atom:link", ARXIV_NAMESPACES):
        href = link_node.attrib.get("href", "")
        if href:
            entry_urls.append(href)
        if link_node.attrib.get("title") == "pdf" and href:
            pdf_url = href
    if not pdf_url and link:
        pdf_url = link.replace("/abs/", "/pdf/") + ".pdf"
        entry_urls.append(pdf_url)

    haystack = f"{title} {abstract}".lower()
    matches = sorted({keyword for keyword in KEYWORDS if keyword in haystack})
    is_robotics_category = primary_category == "cs.RO" or "cs.RO" in categories
    if not matches and not is_robotics_category:
        return None

    score = len(matches) + (4 if is_robotics_category else 0)
    if any(term in haystack for term in ("humanoid", "manipulation", "embodied", "vla")):
        score += 2

    external_links = extract_external_links([title, abstract, comment], entry_urls, doi)
    affiliations = extract_affiliations([title, abstract, comment], external_links)

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
        comment=comment,
        doi=doi,
        external_links=external_links,
        affiliations=affiliations,
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

    for raw_paper in papers:
        paper = enrich_paper_metadata(raw_paper)
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


def filter_papers_by_days(papers: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=days)
    filtered = []
    for paper in papers:
        try:
            published_at = parse_arxiv_datetime(paper["published"])
        except (KeyError, ValueError):
            continue
        if published_at >= cutoff:
            filtered.append(paper)
    return filtered


def range_counts_from_papers(papers: list[dict[str, Any]]) -> dict[str, int]:
    return {
        str(days): len(filter_papers_by_days(papers, days))
        for days in FEED_WINDOWS
    }


def feed_window_cache_name(days: int) -> str:
    return f"feed_days_{days}_{ARXIV_POOL_SIZE}.json"


def cache_feed_window(days: int, papers: list[dict[str, Any]]) -> None:
    cache_set(feed_window_cache_name(days), papers)


def build_feed_windows(refresh: bool = False) -> dict[int, list[dict[str, Any]]]:
    cached_7 = None if refresh else cache_get(feed_window_cache_name(7), max_age_seconds=FEED_CACHE_SECONDS)
    if isinstance(cached_7, list):
        seven_day_papers = cached_7
    else:
        seven_day_papers = rank_feed_papers(fetch_recent_papers(days=7, refresh=refresh))
        cache_feed_window(7, seven_day_papers)

    windows: dict[int, list[dict[str, Any]]] = {}
    for days in FEED_WINDOWS:
        if days == 7:
            papers = seven_day_papers
        else:
            papers = rank_feed_papers(filter_papers_by_days(seven_day_papers, days))
            cache_feed_window(days, papers)
        windows[days] = papers
    return windows


def fetch_feed_window(days: int, refresh: bool = False) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if days in FEED_WINDOWS:
        windows = build_feed_windows(refresh=refresh)
        return windows[days], {str(day): len(windows[day]) for day in FEED_WINDOWS}

    cache_name = feed_window_cache_name(days)
    cached = None if refresh else cache_get(cache_name, max_age_seconds=FEED_CACHE_SECONDS)
    if isinstance(cached, list):
        papers = cached
    else:
        papers = rank_feed_papers(fetch_recent_papers(days=days, refresh=refresh))
        cache_feed_window(days, papers)
    windows = build_feed_windows(refresh=False)
    return papers, {str(day): len(windows[day]) for day in FEED_WINDOWS}


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


def qwen_cache_key(
    papers: list[dict[str, Any]],
    model: str,
    enable_thinking: bool = False,
    thinking_budget: int | None = None,
) -> str:
    seed = json.dumps(
        {
            "prompt_version": 3,
            "model": model,
            "enable_thinking": enable_thinking,
            "thinking_budget": thinking_budget if enable_thinking else None,
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


def build_qwen_prompt(papers: list[dict[str, Any]], days: int | None = None) -> str:
    compact = []
    paper_count = len(papers)
    abstract_limit = 1100 if paper_count <= 12 else 720 if paper_count <= 48 else 420
    for paper in papers:
        compact.append(
            {
                "id": paper["id"],
                "title": paper["title"],
                "authors": paper["authors"][:8],
                "published": paper["published"],
                "categories": paper["categories"],
                "keywords": paper["keyword_matches"],
                "comment": paper.get("comment", "")[:400],
                "affiliations": paper.get("affiliations", [])[:6],
                "external_links": [
                    {
                        "label": link.get("label", ""),
                        "kind": link.get("kind", ""),
                        "url": link.get("url", ""),
                    }
                    for link in paper.get("external_links", [])[:5]
                    if isinstance(link, dict)
                ],
                "abstract": paper["abstract"][:abstract_limit],
            }
        )
    scope_text = f"这是用户选中的近 {days} 天内全部 {paper_count} 篇论文。" if days else f"这是当前范围内全部 {paper_count} 篇论文。"
    return (
        f"{scope_text}请基于全部论文做中文梳理，不要只总结分页首屏。"
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
        "daily_brief、themes 和阅读优先级必须基于该时间范围的完整论文池。"
        "papers 数组要尽量覆盖所有输入论文 id，尤其不能漏掉机器人/具身相关高价值论文。"
        "优先指出工程可用性、机器人系统价值、开源/数据/项目页信号，以及与具身智能的关系。\n\n"
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
    return summarize_range_with_qwen(papers, days=None, refresh=refresh)


def summarize_range_with_qwen(
    papers: list[dict[str, Any]],
    days: int | None = None,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = qwen_config()
    meta = {
        "enabled": bool(config["api_key"]),
        "used": False,
        "model": config["model"],
        "scope": "all_window",
        "scope_days": days,
        "paper_count": len(papers),
        "attempted_models": [],
        "enable_thinking": config["enable_thinking"],
        "thinking_budget": config["thinking_budget"],
        "error": None,
    }
    if not papers:
        return {"daily_brief": "今天没有匹配到新的机器人或具身智能论文。", "themes": [], "papers": []}, meta
    if not config["api_key"]:
        return fallback_summary(papers), meta

    attempts = qwen_attempts(config)
    if not refresh:
        for attempt in attempts:
            cached = cache_get(
                qwen_cache_key(
                    papers,
                    attempt["model"],
                    attempt["enable_thinking"],
                    config["thinking_budget"],
                ),
                max_age_seconds=60 * 60 * 12,
            )
            if cached is not None:
                meta["used"] = True
                meta["cached"] = True
                meta["model"] = attempt["model"]
                meta["enable_thinking"] = attempt["enable_thinking"]
                meta["attempted_models"].append(
                    f"{attempt['model']}{' + thinking' if attempt['enable_thinking'] else ''} cache"
                )
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
        {"role": "user", "content": build_qwen_prompt(papers, days=days)},
    ]

    for attempt in attempts:
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
            cache_set(qwen_cache_key(papers, model, enable_thinking, config["thinking_budget"]), summary)
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


def cached_range_summary(
    papers: list[dict[str, Any]],
    days: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    config = qwen_config()
    meta = {
        "enabled": bool(config["api_key"]),
        "used": False,
        "cached": False,
        "pending": bool(config["api_key"]),
        "model": config["model"],
        "scope": "all_window",
        "scope_days": days,
        "paper_count": len(papers),
        "attempted_models": [],
        "enable_thinking": config["enable_thinking"],
        "thinking_budget": config["thinking_budget"],
        "error": None,
    }
    if not papers or not config["api_key"]:
        meta["pending"] = False
        return None, meta

    for attempt in qwen_attempts(config):
        cached = cache_get(
            qwen_cache_key(
                papers,
                attempt["model"],
                attempt["enable_thinking"],
                config["thinking_budget"],
            ),
            max_age_seconds=60 * 60 * 12,
        )
        if cached is not None:
            meta["used"] = True
            meta["cached"] = True
            meta["pending"] = False
            meta["model"] = attempt["model"]
            meta["enable_thinking"] = attempt["enable_thinking"]
            meta["attempted_models"].append(
                f"{attempt['model']}{' + thinking' if attempt['enable_thinking'] else ''} cache"
            )
            return cached, meta
    return None, meta


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
            paper.get("comment", ""),
            paper.get("doi", ""),
            " ".join(paper.get("categories", [])),
            " ".join(paper.get("keyword_matches", [])),
            " ".join(paper.get("affiliations", [])),
            " ".join(
                f"{link.get('label', '')} {link.get('url', '')}"
                for link in paper.get("external_links", [])
                if isinstance(link, dict)
            ),
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


def counted_values(values: list[str], limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        key = normalize_space(value)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return [
        f"{name} ({count})"
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def build_digest_payload(
    all_papers: list[dict[str, Any]],
    summary: dict[str, Any],
    days: int,
) -> dict[str, Any]:
    merged = merge_summaries(all_papers, summary)
    ranked = rank_feed_papers(merged)
    must_read = []
    for paper in ranked[:5]:
        must_read.append(
            {
                "id": paper.get("id", ""),
                "title": paper.get("title", ""),
                "arxiv_url": paper.get("arxiv_url", ""),
                "one_line": paper.get("one_line", ""),
                "industry_label": paper.get("industry_label", ""),
                "industry_signals": paper.get("industry_signals", [])[:4],
                "external_links": paper.get("external_links", [])[:3],
            }
        )

    signals = counted_values(
        [
            signal
            for paper in ranked
            for signal in paper.get("industry_signals", [])
        ],
        limit=5,
    )
    core_count = sum(1 for paper in ranked if paper.get("industry_level") in ("core", "watch"))
    high_count = sum(1 for paper in ranked if paper.get("read_priority") == "high")
    link_count = sum(1 for paper in ranked if paper.get("external_links"))
    unread_count = len(ranked)

    queue = [
        f"近 {days} 天完整论文池共 {len(ranked)} 篇，优先处理 {core_count or high_count} 篇核心/重点论文",
        f"先确认真机、数据、开源和可复现性；当前可追踪外链 {link_count} 篇",
        f"高优先级 {high_count} 篇适合进入深读或复现候选",
        f"信息流按每批 {DEFAULT_FEED_PAGE_SIZE} 篇浏览，剩余 {max(0, unread_count - DEFAULT_FEED_PAGE_SIZE)} 篇可继续下滑加载",
    ]
    return {
        "scope_days": days,
        "total": len(ranked),
        "daily_brief": summary.get("daily_brief", ""),
        "themes": summary.get("themes", []),
        "must_read": must_read,
        "signals": signals or summary.get("themes", []),
        "queue": queue,
    }


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
        if parsed.path == "/api/summary":
            self.handle_summary(parsed)
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
            minimum=5,
            maximum=24,
        )
        refresh = first(params, "refresh") == "1"
        want_qwen = first(params, "qwen", "1") != "0"

        try:
            all_papers, range_counts = fetch_feed_window(days=days, refresh=refresh)
            total = len(all_papers)
            papers = all_papers[offset : offset + page_size]
            next_offset = offset + len(papers)
            has_more = next_offset < total
            summary = None
            if want_qwen and not refresh:
                summary, qwen_meta = cached_range_summary(all_papers, days=days)
            else:
                qwen_meta = {
                    "enabled": bool(qwen_config()["api_key"]),
                    "used": False,
                    "cached": False,
                    "pending": bool(qwen_config()["api_key"] and want_qwen),
                    "model": qwen_config()["model"],
                    "scope": "all_window",
                    "scope_days": days,
                    "paper_count": total,
                    "error": None,
                }
            if summary is None:
                summary = fallback_summary(all_papers)
            library = load_library()
            merged = attach_library_state(merge_summaries(papers, summary), library)
            digest = build_digest_payload(all_papers, summary, days)
            self.send_json(
                {
                    "generated_at": utc_now().isoformat(),
                    "source": "arXiv",
                    "filters": {"days": days, "offset": offset, "page_size": page_size, "categories": CATEGORIES},
                    "range_counts": range_counts,
                    "feed_cache": {
                        "window_days": days,
                        "strategy": "后台按 1/3/7 天缓存完整论文池，信息流按批读取",
                    },
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
                    "digest": digest,
                    "papers": merged,
                }
            )
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.send_json({"error": f"服务处理失败：{exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_summary(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        days = parse_int(first(params, "days"), default=3, minimum=1, maximum=14)
        refresh = first(params, "refresh") == "1"
        want_qwen = first(params, "qwen", "1") != "0"

        try:
            all_papers, range_counts = fetch_feed_window(days=days, refresh=False)
            if want_qwen:
                summary, qwen_meta = summarize_range_with_qwen(all_papers, days=days, refresh=refresh)
            else:
                summary, qwen_meta = fallback_summary(all_papers), {
                    "enabled": bool(qwen_config()["api_key"]),
                    "used": False,
                    "cached": False,
                    "pending": False,
                    "model": qwen_config()["model"],
                    "scope": "all_window",
                    "scope_days": days,
                    "paper_count": len(all_papers),
                    "error": None,
                }
            merged = merge_summaries(all_papers, summary)
            self.send_json(
                {
                    "generated_at": utc_now().isoformat(),
                    "source": "arXiv",
                    "filters": {"days": days, "categories": CATEGORIES},
                    "range_counts": range_counts,
                    "qwen": qwen_meta,
                    "daily_brief": summary.get("daily_brief", ""),
                    "themes": summary.get("themes", []),
                    "digest": build_digest_payload(all_papers, summary, days),
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
