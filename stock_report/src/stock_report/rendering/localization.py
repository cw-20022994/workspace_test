"""Korean presentation helpers for rendered outputs."""

from __future__ import annotations

import re
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List

ASSET_TYPE_LABELS_KO = {
    "stock": "주식",
    "etf": "ETF",
}

MARKET_LABELS_KO = {
    "US": "미국",
    "KR": "한국",
}

THEME_LABELS_KO = {
    "ai_compute": "AI 연산/가속기",
    "semiconductor_memory": "반도체 메모리",
    "hbf_memory_storage": "HBF 메모리/스토리지",
    "ai_networking_optical": "AI 네트워킹/광통신",
    "semiconductor_equipment": "반도체 장비",
    "ai_power_cooling": "AI 전력/냉각",
    "korea_hbm_hbf": "국내 HBM/HBF",
    "primary_benchmark": "기준 벤치마크",
    "alternate_benchmark": "대체 벤치마크",
    "growth_proxy": "성장주 대표 ETF",
    "small_cap_proxy": "미국 소형주 ETF",
    "sector_proxy": "기술 섹터 ETF",
    "semiconductor_proxy": "반도체 ETF",
    "broad_market_etf": "광범위 시장 ETF",
}

VERDICT_LABELS_KO = {
    "review": "검토",
    "hold": "보류",
    "avoid": "회피",
}

VERDICT_NOTES_KO = {
    "review": "추가 리서치를 진행할 가치가 비교적 높습니다.",
    "hold": "지금 바로 결론을 내리기보다 관찰을 이어가는 편이 낫습니다.",
    "avoid": "현재 데이터 기준으로는 우선순위가 낮습니다.",
}

IMPACT_LABELS_KO = {
    "positive": "긍정",
    "neutral": "중립",
    "mixed": "혼합",
    "negative": "부정",
}

NEWS_CATEGORY_LABELS_KO = {
    "earnings": "실적 관련",
    "guidance": "가이던스 관련",
    "regulatory": "규제/법적 이슈",
    "standardization": "표준화/업계 규격",
    "partnership": "협업/생태계 확대",
    "product_launch": "제품/출시",
    "supply_chain": "공급망/출하",
    "ai_inference": "AI 수요/추론",
    "capital_flows": "자금 유입/유출",
    "price_action": "단기 가격 움직임",
    "volatility": "변동성",
    "etf_market_flow": "ETF 수급/시장 흐름",
    "general": "일반 기업/종목",
}

FIELD_LABELS_KO = {
    "prices.return_20d": "20거래일 수익률",
    "prices.return_60d": "60거래일 수익률",
    "prices.rs_20d": "20거래일 상대강도",
    "prices.price_vs_ma50": "50일 이동평균 대비 가격",
    "prices.drawdown": "고점 대비 낙폭",
    "prices.volatility": "실현 변동성",
    "fundamentals.revenue_growth": "매출 성장률",
    "fundamentals.earnings_growth": "이익 성장률",
    "etf.expense_ratio": "ETF 보수율",
    "etf.holdings_count": "ETF 보유 종목 수",
    "etf.top_10_weight": "ETF 상위 10개 비중",
}

EXACT_TRANSLATIONS_KO = {
    "n/a": "해당 없음",
    "No theme-specific overlay applied.": "별도 테마 가감점은 적용되지 않았습니다.",
    "Theme tracked, but no HBF-specific signals were provided.": "테마는 추적 중이지만 HBF 전용 신호가 충분하지 않습니다.",
    "No explicit risk flags were provided.": "명시적인 위험 신호는 없었습니다.",
    "Elevated realized volatility relative to a typical large-cap profile.": "대형주 평균 대비 실현 변동성이 높은 편입니다.",
    "The asset remains in a deep drawdown from its recent high.": "최근 고점 대비 낙폭이 아직 큰 상태입니다.",
    "Recent headline coverage is sparse, so the narrative may be incomplete.": "최근 기사 수가 적어 서사가 불완전할 수 있습니다.",
    "HBF commercialization evidence is still limited.": "HBF 상용화 근거는 아직 제한적입니다.",
    "Recent HBF narrative appears concentrated in a narrow set of sources.": "최근 HBF 서사가 일부 출처에 편중되어 있습니다.",
    "ETF exposure is narrower than a broad-market benchmark and can diverge sharply from SPY.": "ETF 노출 범위가 광범위 시장 벤치마크보다 좁아 SPY와 괴리가 크게 벌어질 수 있습니다.",
    "high top-holdings concentration": "상위 보유 종목 집중도가 높음",
    "moderate top-holdings concentration": "상위 보유 종목 집중도가 보통 이상",
    "broad diversification across top holdings": "상위 보유 종목 기준 분산도가 비교적 넓음",
    "broad U.S. large-cap benchmark exposure": "미국 대형주 광범위 벤치마크 노출",
    "growth-heavy Nasdaq 100 exposure": "나스닥100 중심 성장주 노출",
    "small-cap U.S. equity exposure": "미국 소형주 노출",
    "technology sector exposure": "기술 섹터 노출",
    "semiconductor sector exposure": "반도체 섹터 노출",
    "Large Blend": "미국 대형 혼합형",
    "Large Growth": "미국 대형 성장형",
    "Technology": "기술주",
    (
        "Live profile generated from Stooq or Naver market data, Google News RSS, "
        "fundamentals from StockAnalysis or Naver Finance when available, "
        "and ETF overview or top-holdings data from StockAnalysis ETF pages when available."
    ): (
        "실시간 프로필은 Stooq 또는 네이버 시세, Google News RSS, "
        "StockAnalysis 또는 네이버 파이낸스 재무 데이터, "
        "그리고 StockAnalysis ETF 개요 및 상위 보유 종목 데이터를 바탕으로 생성되었습니다."
    ),
}


def asset_type_label_ko(asset_type: Any) -> str:
    return ASSET_TYPE_LABELS_KO.get(str(asset_type).lower(), str(asset_type))


def market_label_ko(market: Any) -> str:
    return MARKET_LABELS_KO.get(str(market).upper(), str(market))


def theme_label_ko(theme: Any) -> str:
    value = str(theme)
    return THEME_LABELS_KO.get(value, value)


def verdict_label_ko(verdict: Any) -> str:
    value = str(verdict).lower()
    return VERDICT_LABELS_KO.get(value, value)


def verdict_note_ko(verdict: Any) -> str:
    value = str(verdict).lower()
    return VERDICT_NOTES_KO.get(value, "현재 데이터만으로는 단정하기 어렵습니다.")


def confidence_label_ko(score: Any) -> str:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return "산출 불가"

    if numeric >= 80.0:
        band = "높음"
    elif numeric >= 60.0:
        band = "보통"
    else:
        band = "낮음"
    return "{band} ({score}/100)".format(band=band, score=int(round(numeric)))


def impact_label_ko(impact: Any) -> str:
    value = str(impact).lower()
    return IMPACT_LABELS_KO.get(value, value)


def news_category_label_ko(category: Any) -> str:
    value = str(category).lower()
    return NEWS_CATEGORY_LABELS_KO.get(value, value)


def news_priority_label_ko(priority_score: Any) -> str:
    try:
        numeric = float(priority_score)
    except (TypeError, ValueError):
        return "산출 불가"

    if numeric >= 6.0:
        return "매우 높음"
    if numeric >= 4.5:
        return "높음"
    if numeric >= 3.0:
        return "보통"
    return "낮음"


def field_label_ko(field_name: str) -> str:
    return FIELD_LABELS_KO.get(field_name, field_name)


def translate_text_ko(text: Any) -> str:
    if text in (None, ""):
        return "해당 없음"

    translated = str(text).strip()
    if not translated:
        return "해당 없음"

    exact = EXACT_TRANSLATIONS_KO.get(translated)
    if exact is not None:
        return exact

    translated = re.sub(
        r"Top holdings include ([^;]+); top 10 account for ([\d.]+)% of assets; tracks (.+)",
        r"상위 보유 종목: \1 / 상위 10개 비중: \2% / 추종 기준: \3",
        translated,
    )
    translated = re.sub(
        r"Top holdings include ([^;]+)",
        r"상위 보유 종목: \1",
        translated,
    )
    translated = re.sub(
        r"top 10 account for ([\d.]+)% of assets",
        r"상위 10개 비중: \1%",
        translated,
    )
    translated = re.sub(
        r"tracks (.+)",
        r"추종 기준: \1",
        translated,
    )
    translated = re.sub(
        r"Top 10 ETF holdings account for about ([\d.]+)% of assets\.",
        r"상위 10개 ETF 구성 종목 비중이 약 \1%입니다.",
        translated,
    )
    translated = re.sub(
        r"Missing inputs reduce confidence: (.+)",
        lambda match: "누락된 입력값 때문에 신뢰도가 낮아졌습니다: {value}".format(
            value=_translate_field_csv(match.group(1))
        ),
        translated,
    )
    translated = re.sub(
        r"(\d+) ecosystem partner\(s\)",
        r"생태계 파트너 \1건",
        translated,
    )

    replacements = [
        ("Positive:", "긍정 요인:"),
        ("Caution:", "주의 요인:"),
        ("standardization progress", "표준화 진전"),
        ("AI inference references", "AI 추론 관련 언급"),
        ("commercial sampling", "상용 샘플링"),
        ("shipment evidence", "출하/양산 근거"),
        ("concept-heavy coverage", "개념 소개성 기사 비중이 높음"),
        ("single-source narrative risk", "일부 출처에 서사가 집중됨"),
        ("commercial proof still limited", "상용화 근거가 아직 제한적임"),
        ("gross margin", "매출총이익률"),
        ("operating margin", "영업이익률"),
        ("forward P/E", "선행 PER"),
        ("EV/sales", "EV/매출"),
        ("expense ratio", "총보수"),
        ("low leverage", "레버리지 부담 낮음"),
        ("moderate leverage", "레버리지 부담 보통"),
        ("elevated leverage", "레버리지 부담 높음"),
        ("mixed-positive", "중기적으로 양호"),
        ("constructive", "우호적"),
        ("positive", "긍정"),
        ("mixed", "혼조"),
        ("weak", "약함"),
    ]
    for source, target in replacements:
        translated = translated.replace(source, target)

    return translated


def translate_list_ko(values: Iterable[Any]) -> List[str]:
    return [translate_text_ko(value) for value in values]


def build_score_guide_ko() -> Dict[str, Any]:
    return {
        "종합점수": "0점부터 100점까지이며 높을수록 현재 데이터 기준으로 추가 검토 매력이 높다는 뜻입니다.",
        "판정": {
            "검토": "70점 이상. 추가 리서치 우선순위가 높은 편입니다.",
            "보류": "50점 이상 70점 미만. 장단점이 섞여 있어 관찰이 더 필요합니다.",
            "회피": "50점 미만. 현재 데이터만 보면 우선순위가 낮습니다.",
        },
        "신뢰도": "투자 성공 확률이 아니라 데이터 충분성, 최신성, 신호 일관성을 점수화한 값입니다.",
        "추세점수": "수익률, 이동평균 대비 위치, 상대강도, 낙폭, 변동성을 반영합니다.",
        "기초체력점수": "성장률, 수익성, 밸류에이션, 레버리지 또는 ETF 보수율을 반영합니다.",
        "뉴스점수": "최근 기사 영향도와 이벤트 성격을 반영합니다.",
        "리스크점수": "변동성, 낙폭, 밸류에이션 부담, 데이터 신선도, 위험 플래그를 반영합니다.",
        "테마가감점": "HBF 같은 특수 테마에서 표준화, 상용화, 생태계 확대 여부를 추가 반영합니다.",
    }


def build_profile_guide_ko() -> Dict[str, Any]:
    return {
        "prices": "가격 지표입니다. 수익률, 상대강도, 이동평균 대비 위치, 낙폭, 변동성을 포함합니다.",
        "fundamentals": "재무 지표입니다. 성장률, 수익성, 밸류에이션 등 사용 가능한 항목만 채웁니다.",
        "etf": "ETF 전용 지표입니다. 분류, 운용사, 보수율, 운용자산, 구성 종목 집중도 등을 포함합니다.",
        "news": "최근 수집된 뉴스입니다. headline은 원문 제목, category는 기사 유형, priority_score는 내부 중요도 정렬 점수입니다.",
        "freshness": "각 데이터의 기준일과 데이터 경과일을 보여줍니다.",
        "theme_signals": "HBF 등 특정 테마에서만 쓰는 보조 신호입니다.",
    }


def display_name(name: Any, symbol: Any) -> str:
    return "{name} ({symbol})".format(name=str(name), symbol=str(symbol))


def _translate_field_csv(value: str) -> str:
    items = [field_label_ko(item.strip()) for item in value.split(",") if item.strip()]
    return ", ".join(items)
