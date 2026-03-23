"""Google News RSS connector and simple headline heuristics."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from datetime import timezone
from typing import Dict
from typing import List
from typing import Optional
import re
import xml.etree.ElementTree as ET

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.http import HttpClient
from stock_report.models import AssetDefinition
from stock_report.models import NewsItem

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
HBF_NEWS_THEMES = {"hbf_memory_storage", "korea_hbm_hbf"}

THEME_HINTS = {
    "ai_compute": ["AI", "GPU", "accelerator"],
    "semiconductor_memory": ["semiconductor", "memory", "HBM"],
    "hbf_memory_storage": ["HBF", "\"high bandwidth flash\"", "AI inference"],
    "ai_networking_optical": ["AI", "networking", "optical"],
    "semiconductor_equipment": ["semiconductor equipment", "wafer", "fab"],
    "ai_power_cooling": ["AI data center", "power", "cooling"],
    "korea_hbm_hbf": ["HBM", "HBF", "semiconductor"],
}

POSITIVE_KEYWORDS = {
    "beat",
    "beats",
    "strong",
    "surge",
    "expand",
    "expands",
    "partnership",
    "partner",
    "partners",
    "collaboration",
    "collaborate",
    "ramp",
    "shipment",
    "shipments",
    "sampling",
    "sample",
    "approval",
    "approved",
    "win",
    "wins",
    "launch",
    "launches",
    "standardization",
    "interoperability",
    "upgrade",
}

NEGATIVE_KEYWORDS = {
    "miss",
    "misses",
    "delay",
    "delays",
    "delayed",
    "cut",
    "cuts",
    "downgrade",
    "downgraded",
    "probe",
    "lawsuit",
    "fine",
    "ban",
    "weak",
    "slump",
    "fall",
    "falls",
    "slowdown",
    "risk",
    "warns",
    "warning",
}

TAG_PATTERNS = {
    "earnings": re.compile(r"\b(earnings|revenue|profit|guidance)\b", re.I),
    "guidance": re.compile(r"\b(guidance|forecast|outlook)\b", re.I),
    "product_launch": re.compile(r"\b(launch|introduce|release|unveil)\b", re.I),
    "standardization": re.compile(r"\b(standardization|standard|interoperability|jedec|consortium)\b", re.I),
    "regulatory": re.compile(r"\b(regulator|regulatory|antitrust|probe|ban|tariff|lawsuit)\b", re.I),
    "supply_chain": re.compile(
        r"\b(supply chain|capacity|shortage|shipment|production|ramp|fab)\b",
        re.I,
    ),
    "partnership": re.compile(r"\b(partner|partnership|collaboration|ecosystem)\b", re.I),
    "ai_inference": re.compile(r"\b(ai inference|inference|ai)\b", re.I),
    "capital_flows": re.compile(r"\b(inflow|inflows|outflow|outflows|fund flow|flows)\b", re.I),
    "price_action": re.compile(
        r"\b(up today|down today|bullish|bearish|rally|sell-off|soars|slides|surges|drops|gains|falls)\b",
        re.I,
    ),
}

NAME_TOKEN_STOPWORDS = {
    "inc",
    "corp",
    "corporation",
    "company",
    "co",
    "limited",
    "ltd",
    "plc",
    "holdings",
    "group",
    "class",
    "core",
    "select",
    "trust",
    "fund",
    "etf",
    "shares",
}

LOW_SIGNAL_PATTERNS = [
    re.compile(r"\b(stock price|quote|chart|historical price|price target)\b", re.I),
    re.compile(r"\b(analyst ratings?|analyst forecast)\b", re.I),
    re.compile(r"\b(should you buy|buy[, ]+sell[, ]+or hold|price prediction)\b", re.I),
]

CATEGORY_PRIORITY_BASE = {
    "earnings": 5.0,
    "guidance": 4.8,
    "regulatory": 4.7,
    "standardization": 4.4,
    "supply_chain": 4.2,
    "partnership": 4.1,
    "product_launch": 3.9,
    "ai_inference": 3.6,
    "capital_flows": 2.5,
    "etf_market_flow": 2.2,
    "volatility": 1.8,
    "price_action": 1.4,
    "general": 2.0,
}


class GoogleNewsClient:
    """Fetch ticker-related headlines from Google News RSS."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_news(
        self,
        asset: AssetDefinition,
        days: int = 7,
        limit: int = 5,
    ) -> List[NewsItem]:
        query = _build_query(asset, days)
        text = self.http_client.get_text(
            GOOGLE_NEWS_RSS_URL,
            params={
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
        )

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ConnectorError("Could not parse Google News RSS response.") from exc

        channel = root.find("channel")
        if channel is None:
            return []

        candidates = []
        seen_signatures = []
        for item in channel.findall("item"):
            title = _clean_headline(item.findtext("title"), item.findtext("source"))
            if not title:
                continue

            description = _clean_description(item.findtext("description"))
            if not _is_relevant_news(asset, title, description):
                continue

            source = item.findtext("source") or "unknown"
            if _is_low_signal_news(title, source):
                continue

            signature = _headline_signature(title)
            if _is_duplicate_signature(signature, seen_signatures):
                continue
            seen_signatures.append(signature)

            published_at = _to_iso8601(item.findtext("pubDate"))
            tags = _extract_tags(title)
            impact = _estimate_impact(title)
            relevance_score = _relevance_score(asset, title, description)
            category = _classify_news_category(asset, title, tags)
            priority_score = _estimate_priority_score(
                asset,
                title,
                impact,
                tags,
                category,
                relevance_score,
            )
            materiality = _estimate_materiality(
                title,
                tags,
                relevance_score=relevance_score,
                priority_score=priority_score,
                category=category,
                impact=impact,
            )

            candidates.append(
                NewsItem(
                    headline=title,
                    summary_ko=_build_summary_ko(asset, impact, category),
                    source=source,
                    published_at=published_at,
                    impact=impact,
                    category=category,
                    priority_score=priority_score,
                    materiality=materiality,
                    tags=tags,
                )
            )

        ordered = sorted(
            candidates,
            key=lambda item: (
                item.priority_score,
                item.materiality,
                item.published_at,
            ),
            reverse=True,
        )

        return ordered[:limit]


def _build_query(asset: AssetDefinition, days: int) -> str:
    parts = ['"{name}"'.format(name=asset.name)]
    if asset.asset_type == "etf":
        parts.append('"{symbol} ETF"'.format(symbol=asset.symbol))
        if not any(
            token in asset.name.lower() for token in ("etf", "fund", "trust")
        ):
            parts.append('"{symbol} fund"'.format(symbol=asset.symbol))
    elif "." not in asset.symbol:
        parts.append(asset.symbol)

    query = "(" + " OR ".join(parts) + ")"
    theme_hints = THEME_HINTS.get(asset.theme, [])
    if theme_hints:
        query += " (" + " OR ".join(theme_hints) + ")"
    query += " when:{days}d".format(days=days)
    return query


def _clean_headline(title: Optional[str], source: Optional[str]) -> str:
    if not title:
        return ""
    cleaned = str(title).strip()
    if source:
        suffix = " - {source}".format(source=source.strip())
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned


def _clean_description(description: Optional[str]) -> str:
    if not description:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", str(description))
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _to_iso8601(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value


def _estimate_impact(title: str) -> str:
    lowered = title.lower()
    positive = any(keyword in lowered for keyword in POSITIVE_KEYWORDS)
    negative = any(keyword in lowered for keyword in NEGATIVE_KEYWORDS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def _extract_tags(title: str) -> List[str]:
    tags = []
    for tag, pattern in TAG_PATTERNS.items():
        if pattern.search(title):
            tags.append(tag)
    return tags


def _estimate_materiality(
    title: str,
    tags: List[str],
    relevance_score: float = 0.0,
    priority_score: float = 0.0,
    category: str = "general",
    impact: str = "neutral",
) -> float:
    score = 0.30
    if len(title.split()) >= 8:
        score += 0.03
    score += min(priority_score * 0.08, 0.45)
    score += min(max(relevance_score - 2.0, 0.0) * 0.04, 0.12)
    if impact != "neutral":
        score += 0.05
    if category in {"earnings", "guidance", "regulatory"}:
        score += 0.08
    elif len(tags) >= 2:
        score += 0.04
    return round(min(score, 1.0), 2)


def _is_relevant_news(asset: AssetDefinition, title: str, description: str) -> bool:
    return _relevance_score(asset, title, description) >= 2.0


def _relevance_score(asset: AssetDefinition, title: str, description: str) -> float:
    text = "{title} {description}".format(
        title=title,
        description=description,
    ).lower().strip()
    score = 0.0

    full_name = asset.name.lower().strip()
    if full_name and full_name in text:
        score += 4.0

    symbol = asset.symbol.lower().strip()
    if symbol and re.search(r"\b{symbol}\b".format(symbol=re.escape(symbol)), text):
        score += 3.0

    token_hits = 0
    for token in _asset_name_tokens(asset):
        if re.search(r"\b{token}\b".format(token=re.escape(token)), text):
            token_hits += 1
    score += min(float(token_hits), 3.0)

    if asset.asset_type == "etf" and "etf" in text:
        score += 0.5

    for hint in THEME_HINTS.get(asset.theme, []):
        normalized_hint = hint.replace('"', "").lower().strip()
        if normalized_hint and normalized_hint in text:
            score += 0.25

    return score


def _asset_name_tokens(asset: AssetDefinition) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", asset.name.lower())
    return [
        token
        for token in cleaned.split()
        if len(token) >= 3 and token not in NAME_TOKEN_STOPWORDS
    ]


def _is_low_signal_news(title: str, source: str) -> bool:
    combined = "{title} {source}".format(title=title, source=source).strip()
    return any(pattern.search(combined) for pattern in LOW_SIGNAL_PATTERNS)


def _headline_signature(title: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return [token for token in cleaned.split() if len(token) >= 3]


def _is_duplicate_signature(signature: List[str], seen_signatures: List[List[str]]) -> bool:
    if not signature:
        return True

    current = set(signature)
    for previous in seen_signatures:
        prior = set(previous)
        if current == prior:
            return True
        overlap = len(current.intersection(prior))
        baseline = min(len(current), len(prior))
        if baseline > 0 and (overlap / float(baseline)) >= 0.85:
            return True
    return False


def _classify_news_category(
    asset: AssetDefinition,
    title: str,
    tags: List[str],
) -> str:
    lowered = title.lower()
    ordered_tags = [
        "earnings",
        "guidance",
        "regulatory",
        "standardization",
        "partnership",
        "product_launch",
        "supply_chain",
        "ai_inference",
        "capital_flows",
        "price_action",
    ]
    for tag in ordered_tags:
        if tag in tags:
            return tag
    if "volatility" in lowered or "volatile" in lowered:
        return "volatility"
    if asset.asset_type == "etf":
        return "etf_market_flow"
    return "general"


def _estimate_priority_score(
    asset: AssetDefinition,
    title: str,
    impact: str,
    tags: List[str],
    category: str,
    relevance_score: float,
) -> float:
    score = CATEGORY_PRIORITY_BASE.get(category, CATEGORY_PRIORITY_BASE["general"])
    score += min(relevance_score * 0.35, 1.75)

    if impact in {"positive", "negative", "mixed"}:
        score += 0.35
    if category in {"earnings", "guidance"}:
        score += 0.45
    if category == "regulatory":
        score += 0.35
    if category in {"price_action", "volatility"}:
        score -= 0.15
    if asset.asset_type == "etf" and category == "capital_flows":
        score += 0.35
    if asset.theme in HBF_NEWS_THEMES and category in {
        "standardization",
        "partnership",
        "supply_chain",
        "product_launch",
        "ai_inference",
    }:
        score += 0.40
    if "why is " in title.lower() and " today" in title.lower():
        score -= 0.25
    if len(tags) >= 2:
        score += 0.15
    return round(max(score, 0.0), 2)


def _build_summary_ko(
    asset: AssetDefinition,
    impact: str,
    category: str,
) -> str:
    subject = asset.name if asset.asset_type == "stock" else display_etf_name(asset.name)
    event_label = _category_label_ko(category)

    impact_label = {
        "positive": "긍정",
        "neutral": "중립",
        "mixed": "혼조",
        "negative": "부정",
    }.get(impact, impact)

    return "{subject}에 대한 {event}로, 현재 영향 판단은 {impact}입니다.".format(
        subject=subject,
        event=event_label,
        impact=impact_label,
    )


def display_etf_name(name: str) -> str:
    if "ETF" in name.upper():
        return name
    return "{name} ETF".format(name=name)


def _category_label_ko(category: str) -> str:
    return {
        "earnings": "실적/가이던스 관련 뉴스",
        "guidance": "실적 전망/가이던스 관련 뉴스",
        "regulatory": "규제/법적 이슈 관련 뉴스",
        "standardization": "표준화 또는 업계 규격 관련 뉴스",
        "partnership": "협업/생태계 확대 관련 뉴스",
        "product_launch": "제품/출시 관련 뉴스",
        "supply_chain": "공급망/출하 관련 뉴스",
        "ai_inference": "AI 수요 또는 추론 관련 뉴스",
        "capital_flows": "자금 유입/유출 관련 뉴스",
        "price_action": "단기 가격 움직임 설명 기사",
        "volatility": "변동성 관련 뉴스",
        "etf_market_flow": "ETF 수급/시장 흐름 관련 뉴스",
        "general": "회사/종목 관련 뉴스",
    }.get(category, "회사/종목 관련 뉴스")
