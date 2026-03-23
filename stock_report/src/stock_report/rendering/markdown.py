"""Report rendering helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List

from stock_report.models import AnalysisInput
from stock_report.models import AssetDefinition
from stock_report.models import ScoreBreakdown
from stock_report.models import Watchlist
from stock_report.rendering.localization import asset_type_label_ko
from stock_report.rendering.localization import build_score_guide_ko
from stock_report.rendering.localization import confidence_label_ko
from stock_report.rendering.localization import display_name
from stock_report.rendering.localization import impact_label_ko
from stock_report.rendering.localization import market_label_ko
from stock_report.rendering.localization import news_category_label_ko
from stock_report.rendering.localization import news_priority_label_ko
from stock_report.rendering.localization import theme_label_ko
from stock_report.rendering.localization import translate_text_ko
from stock_report.rendering.localization import verdict_label_ko
from stock_report.rendering.localization import verdict_note_ko


def render_markdown_report(
    watchlist: Watchlist,
    asset: AssetDefinition,
    analysis: AnalysisInput,
    scores: ScoreBreakdown,
) -> str:
    """Render a single-symbol Markdown report."""

    benchmark_symbol = analysis.benchmark_symbol or watchlist.defaults.get(
        "benchmark_symbol", "SPY"
    )
    theme_note = watchlist.theme_notes.get(asset.theme, {})
    benchmark_label = _benchmark_label(watchlist, benchmark_symbol)
    score_guide = build_score_guide_ko()

    summary = _build_summary(asset, scores, theme_note)
    short_trend_view = _describe_trend(scores.trend_score)
    medium_trend_view = _describe_trend(scores.trend_score, medium=True)
    profitability_view = _describe_profitability(analysis.fundamentals)
    valuation_view = _describe_valuation(analysis.fundamentals, analysis.etf)
    balance_sheet_view = _describe_balance_sheet(analysis.fundamentals)
    concentration_view = _describe_concentration(asset, analysis)
    holdings_note = _holdings_note(asset, analysis, theme_note)

    news_lines = _render_news_lines(analysis.news)
    risk_lines = _render_risk_lines(analysis, scores)
    freshness = analysis.freshness

    lines = [
        "# {name} 리서치 리포트".format(name=display_name(asset.name, asset.symbol)),
        "",
        "- 회사/종목명: {value}".format(value=asset.name),
        "- 티커: {value}".format(value=asset.symbol),
        "- 자산 구분: {value}".format(value=asset_type_label_ko(asset.asset_type)),
        "- 시장: {value}".format(value=market_label_ko(asset.market)),
        "- 테마: {value}".format(value=theme_label_ko(asset.theme)),
        "- 리포트 생성 시각(UTC): {value}".format(value=_text(analysis.report_time_utc)),
        "- 비교 기준: {value}".format(value=benchmark_label),
        "- 최종 판단: {value}".format(value=verdict_label_ko(scores.verdict)),
        "- 종합 점수: {value}/100".format(value=_score_text(scores.total_score)),
        "- 신뢰도: {value}".format(value=confidence_label_ko(scores.confidence_score)),
        "",
        "## 한줄 요약",
        "",
        summary,
        "",
        "## 읽는 법",
        "",
        "- 종합 점수: {value}".format(value=score_guide["종합점수"]),
        "- 판정: 검토 / 보류 / 회피 중 하나입니다. 현재 결과는 `{value}`입니다.".format(
            value=verdict_label_ko(scores.verdict)
        ),
        "- 신뢰도: {value}".format(value=score_guide["신뢰도"]),
        "- 테마 가감점: {value}".format(value=score_guide["테마가감점"]),
        "",
        "## 최근 변화",
        "",
        "- 최근 5거래일 수익률: {value}".format(value=_percent(analysis.prices.get("return_5d"))),
        "- 최근 20거래일 수익률: {value}".format(value=_percent(analysis.prices.get("return_20d"))),
        "- 벤치마크 대비 20거래일 상대강도: {value}".format(value=_percent(analysis.prices.get("rs_20d"))),
        "- 실현 변동성: {value}".format(value=_percent(analysis.prices.get("volatility"))),
        "- 최근 고점 대비 낙폭: {value}".format(value=_percent(analysis.prices.get("drawdown"))),
        "",
        "## 주요 뉴스",
        "",
        "- 아래 기사는 내부 중요도 순으로 정렬했습니다.",
        "",
    ]

    lines.extend(news_lines)
    lines.extend(
        [
            "",
            "## 추세 분석",
            "",
            "- 단기 추세 판단: {value}".format(value=short_trend_view),
            "- 중기 추세 판단: {value}".format(value=medium_trend_view),
            "- 보조 지표:",
            "  - 20일 이동평균 대비 가격: {value}".format(value=_ratio(analysis.prices.get("price_vs_ma20"))),
            "  - 50일 이동평균 대비 가격: {value}".format(value=_ratio(analysis.prices.get("price_vs_ma50"))),
            "  - 200일 이동평균 대비 가격: {value}".format(value=_ratio(analysis.prices.get("price_vs_ma200"))),
            "",
            "## 재무/기초체력 요약",
            "",
            "- 매출 성장률: {value}".format(value=_percent(analysis.fundamentals.get("revenue_growth"))),
            "- 이익 성장률: {value}".format(value=_percent(analysis.fundamentals.get("earnings_growth"))),
            "- 수익성: {value}".format(value=profitability_view),
            "- 밸류에이션: {value}".format(value=valuation_view),
            "- 재무 건전성: {value}".format(value=balance_sheet_view),
            "",
            "## ETF 참고 사항",
            "",
            "- ETF 분류: {value}".format(value=_text_ko(analysis.etf.get("category"))),
            "- 운용사: {value}".format(value=_text_ko(analysis.etf.get("provider"))),
            "- 운용자산(AUM): {value}".format(value=_money(analysis.etf.get("aum"))),
            "- 총보수: {value}".format(value=_percent(analysis.etf.get("expense_ratio"))),
            "- 보유 종목 수: {value}".format(value=_text_ko(analysis.etf.get("holdings_count"))),
            "- 상위 10개 비중: {value}".format(value=_percent(analysis.etf.get("top_10_weight"))),
            "- 집중도 해석: {value}".format(value=concentration_view),
            "- 구성 종목/섹터 메모: {value}".format(value=holdings_note),
            "",
            "## 점수표",
            "",
            "- 추세 점수: {value}/100".format(value=_score_text(scores.trend_score)),
            "- 기초체력 점수: {value}/100".format(value=_score_text(scores.fundamentals_score)),
            "- 뉴스 점수: {value}/100".format(value=_score_text(scores.news_score)),
            "- 리스크 점수: {value}/100".format(value=_score_text(scores.risk_score)),
            "- 테마 가감점: {value}".format(value=_signed_score(scores.theme_overlay)),
            "- 테마 가감점 근거: {value}".format(value=translate_text_ko(scores.overlay_rationale)),
            "",
            "## 핵심 위험 요인",
            "",
        ]
    )
    lines.extend(risk_lines)
    lines.extend(
        [
            "",
            "## 최종 해석",
            "",
            _build_bottom_line(asset, scores),
            "",
            "## 데이터 기준 시점",
            "",
            "- 가격 데이터 기준일: {value}".format(value=_text_ko(freshness.get("price_data_as_of"))),
            "- 재무 데이터 기준일: {value}".format(value=_text_ko(freshness.get("fundamentals_data_as_of"))),
            "- ETF 데이터 기준일: {value}".format(value=_text_ko(freshness.get("etf_data_as_of"))),
            "- 뉴스 수집 구간: {value}".format(value=_text_ko(freshness.get("news_window"))),
            "",
            "이 리포트는 투자 판단 보조용이며, 투자 권유가 아닙니다.",
        ]
    )
    return "\n".join(lines)


def build_scorecard(
    watchlist: Watchlist,
    asset: AssetDefinition,
    analysis: AnalysisInput,
    scores: ScoreBreakdown,
) -> Dict[str, Any]:
    """Build a machine-readable scorecard payload."""

    benchmark_symbol = analysis.benchmark_symbol or watchlist.defaults.get(
        "benchmark_symbol", "SPY"
    )
    return {
        "asset": {
            "symbol": asset.symbol,
            "name": asset.name,
            "display_name": display_name(asset.name, asset.symbol),
            "asset_type": asset.asset_type,
            "asset_type_label_ko": asset_type_label_ko(asset.asset_type),
            "market": asset.market,
            "market_label_ko": market_label_ko(asset.market),
            "theme": asset.theme,
            "theme_label_ko": theme_label_ko(asset.theme),
            "benchmark_symbol": benchmark_symbol,
        },
        "scores": scores.to_dict(),
        "prices": analysis.prices,
        "fundamentals": analysis.fundamentals,
        "etf": analysis.etf,
        "freshness": analysis.freshness,
        "risk_flags": analysis.risk_flags,
        "notes": analysis.notes,
        "guide_ko": build_score_guide_ko(),
        "readable_ko": {
            "종목개요": {
                "회사/종목명": asset.name,
                "티커": asset.symbol,
                "표시명": display_name(asset.name, asset.symbol),
                "자산구분": asset_type_label_ko(asset.asset_type),
                "시장": market_label_ko(asset.market),
                "테마": theme_label_ko(asset.theme),
                "비교기준": benchmark_symbol,
            },
            "핵심판단": {
                "종합점수": "{value}/100".format(value=_score_text(scores.total_score)),
                "최종판단": verdict_label_ko(scores.verdict),
                "판정설명": verdict_note_ko(scores.verdict),
                "신뢰도": confidence_label_ko(scores.confidence_score),
                "테마가감점": _signed_score(scores.theme_overlay),
                "테마가감점근거": translate_text_ko(scores.overlay_rationale),
            },
            "점수세부": {
                "추세점수": _score_text(scores.trend_score),
                "기초체력점수": _score_text(scores.fundamentals_score),
                "뉴스점수": _score_text(scores.news_score),
                "리스크점수": _score_text(scores.risk_score),
            },
            "위험요인": [translate_text_ko(item) for item in analysis.risk_flags],
            "데이터메모": translate_text_ko(analysis.notes),
        },
    }


def _build_summary(
    asset: AssetDefinition, scores: ScoreBreakdown, theme_note: Dict[str, str]
) -> str:
    theme_rationale = translate_text_ko(theme_note.get("rationale"))
    overlay_sentence = ""
    if scores.theme_overlay != 0:
        overlay_sentence = " 테마 가감점은 {value}점이며, 이유는 {reason}입니다.".format(
            value=_signed_score(scores.theme_overlay),
            reason=translate_text_ko(scores.overlay_rationale),
        )

    return (
        "{name}은 현재 종합 점수 {score}/100점, 최종 판단 `{verdict}`, 신뢰도 "
        "{confidence}로 평가됩니다. 단기 추세는 {trend}으로 해석되며, 기본 판정은 "
        "{verdict_note} 테마 맥락은 {theme_rationale}.{overlay_sentence}"
    ).format(
        name=display_name(asset.name, asset.symbol),
        score=_score_text(scores.total_score),
        verdict=verdict_label_ko(scores.verdict),
        confidence=confidence_label_ko(scores.confidence_score),
        trend=_describe_trend(scores.trend_score),
        verdict_note=verdict_note_ko(scores.verdict),
        theme_rationale=theme_rationale,
        overlay_sentence=overlay_sentence,
    )


def _build_bottom_line(asset: AssetDefinition, scores: ScoreBreakdown) -> str:
    return (
        "{name}의 이번 결론은 `{verdict}`입니다. 종합 점수는 {score}/100점이고, "
        "기본 점수는 {base_score}/100점, 테마 가감점은 {overlay}입니다. 다음 확인 "
        "포인트는 최근 뉴스가 실제 실적과 수익성으로 이어지는지, 그리고 위험 요인이 "
        "완화되는지 여부입니다."
    ).format(
        name=display_name(asset.name, asset.symbol),
        verdict=verdict_label_ko(scores.verdict),
        score=_score_text(scores.total_score),
        base_score=_score_text(scores.base_total_score),
        overlay=_signed_score(scores.theme_overlay),
    )


def _render_news_lines(news_items: List[Any]) -> List[str]:
    rendered = []
    for index, item in enumerate(news_items[:3], start=1):
        rendered.append(
            (
                "{index}. [{priority} | {category}] {summary} | 원문: {headline} | "
                "출처: {source} | 시각: {published_at} | 영향: {impact}"
            ).format(
                index=index,
                priority=news_priority_label_ko(getattr(item, "priority_score", None)),
                category=news_category_label_ko(getattr(item, "category", "general")),
                summary=item.summary_ko or "해당 없음",
                headline=item.headline or "해당 없음",
                source=item.source or "해당 없음",
                published_at=item.published_at or "해당 없음",
                impact=impact_label_ko(item.impact or "neutral"),
            )
        )
    while len(rendered) < 3:
        rendered.append("{index}. 해당 없음".format(index=len(rendered) + 1))
    return rendered


def _render_risk_lines(analysis: AnalysisInput, scores: ScoreBreakdown) -> List[str]:
    risks = list(analysis.risk_flags)
    if scores.missing_inputs:
        risks.append(
            "Missing inputs reduce confidence: {value}".format(
                value=", ".join(scores.missing_inputs[:3])
            )
        )
    if not risks:
        risks = ["No explicit risk flags were provided."]
    return ["- {value}".format(value=translate_text_ko(item)) for item in risks[:3]]


def _describe_trend(score: float, medium: bool = False) -> str:
    if score >= 70.0:
        return "우호적" if medium else "긍정적"
    if score >= 55.0:
        return "대체로 양호" if medium else "혼조"
    return "약함"


def _describe_profitability(fundamentals: Dict[str, Any]) -> str:
    gross_margin = fundamentals.get("gross_margin")
    operating_margin = fundamentals.get("operating_margin")
    if gross_margin is None and operating_margin is None:
        return "해당 없음"
    gross_text = _percent(gross_margin)
    operating_text = _percent(operating_margin)
    return "매출총이익률 {gross}, 영업이익률 {operating}".format(
        gross=gross_text, operating=operating_text
    )


def _describe_valuation(
    fundamentals: Dict[str, Any], etf_metrics: Dict[str, Any]
) -> str:
    forward_pe = fundamentals.get("forward_pe")
    ev_to_sales = fundamentals.get("ev_to_sales")
    expense_ratio = etf_metrics.get("expense_ratio")

    parts = []
    if forward_pe is not None:
        parts.append("선행 PER {value}".format(value=_number(forward_pe)))
    if ev_to_sales is not None:
        parts.append("EV/매출 {value}".format(value=_number(ev_to_sales)))
    if expense_ratio is not None:
        parts.append("총보수 {value}".format(value=_percent(expense_ratio)))
    return ", ".join(parts) if parts else "해당 없음"


def _describe_balance_sheet(fundamentals: Dict[str, Any]) -> str:
    net_debt = fundamentals.get("net_debt_to_ebitda")
    if net_debt is None:
        return "해당 없음"
    if float(net_debt) <= 1.0:
        return "레버리지 부담 낮음"
    if float(net_debt) <= 2.0:
        return "레버리지 부담 보통"
    return "레버리지 부담 높음"


def _describe_concentration(asset: AssetDefinition, analysis: AnalysisInput) -> str:
    if asset.asset_type != "etf":
        return "해당 없음"
    concentration = analysis.etf.get("concentration")
    top_10_weight = analysis.etf.get("top_10_weight")
    sector_bias = analysis.etf.get("sector_bias")
    parts = []
    if concentration:
        parts.append(translate_text_ko(concentration))
    if top_10_weight is not None:
        parts.append("상위 10개 비중 {value}".format(value=_percent(top_10_weight)))
    if sector_bias:
        parts.append(translate_text_ko(sector_bias))
    return ", ".join(parts) if parts else "해당 없음"


def _holdings_note(
    asset: AssetDefinition,
    analysis: AnalysisInput,
    theme_note: Dict[str, str],
) -> str:
    if asset.asset_type != "etf":
        return translate_text_ko(theme_note.get("rationale"))
    etf_note = analysis.etf.get("holdings_note")
    if etf_note:
        return translate_text_ko(str(etf_note))
    return translate_text_ko(theme_note.get("rationale"))


def _benchmark_label(watchlist: Watchlist, benchmark_symbol: str) -> str:
    asset = watchlist.assets.get(str(benchmark_symbol).upper())
    if asset is None:
        return str(benchmark_symbol)
    return display_name(asset.name, asset.symbol)


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)


def _text_ko(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return translate_text_ko(value)


def _percent(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return "{value:.1f}%".format(value=float(value))


def _ratio(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return "{value:.2f}배".format(value=float(value))


def _number(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return "{value:.1f}".format(value=float(value))


def _money(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    amount = float(value)
    if amount >= 1_000_000_000_000:
        return "${value:.2f}T".format(value=amount / 1_000_000_000_000)
    if amount >= 1_000_000_000:
        return "${value:.2f}B".format(value=amount / 1_000_000_000)
    if amount >= 1_000_000:
        return "${value:.2f}M".format(value=amount / 1_000_000)
    return "${value:,.0f}".format(value=amount)


def _score_text(value: Any) -> str:
    return "{value:.1f}".format(value=float(value))


def _signed_score(value: Any) -> str:
    return "{value:+.1f}".format(value=float(value))
