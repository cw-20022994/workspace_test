from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverviewMetric:
    label: str
    value: str
    detail: str


@dataclass(frozen=True)
class PositionRow:
    market: str
    strategy: str
    entry_price: str
    mark_price: str
    pnl: str
    hold_time: str


@dataclass(frozen=True)
class SignalRow:
    market: str
    timeframe: str
    status: str
    progress_text: str
    progress_percent: int


@dataclass(frozen=True)
class ActivityRow:
    time_text: str
    title: str
    detail: str


@dataclass(frozen=True)
class ExchangeRow:
    name: str
    note: str
    badge: str


@dataclass(frozen=True)
class StrategyField:
    label: str
    value: float
    minimum: float
    maximum: float
    decimals: int = 2
    suffix: str = ""


@dataclass(frozen=True)
class PrototypeSnapshot:
    title: str
    subtitle: str
    profile_name: str
    mode_badge: str
    metrics: list[OverviewMetric]
    positions: list[PositionRow]
    signals: list[SignalRow]
    activities: list[ActivityRow]
    exchanges: list[ExchangeRow]
    strategy_fields: list[StrategyField]
    risk_fields: list[StrategyField]
    market_pulse: list[float]


def build_prototype_snapshot() -> PrototypeSnapshot:
    return PrototypeSnapshot(
        title="코인 파트너",
        subtitle=(
            "구매자가 직접 거래소 키와 기준값을 넣고 사용할 수 있는 "
            "자동매매 앱 예시 화면입니다."
        ),
        profile_name="직접 설정형 기본 프로필",
        mode_badge="UI 프로토타입",
        metrics=[
            OverviewMetric("오늘 수익", "+184,200 KRW", "예시 데이터 기준"),
            OverviewMetric("자동매매 상태", "대기 중", "30초마다 조건 확인"),
            OverviewMetric("감시 코인", "3개", "BTC · ETH · XRP"),
            OverviewMetric("1회 매수금액", "50,000 KRW", "구매자가 직접 수정 가능"),
        ],
        positions=[
            PositionRow("KRW-BTC", "눌림목", "128,420,000", "129,180,000", "+0.59%", "18분"),
            PositionRow("KRW-ETH", "돌파", "4,180,000", "4,245,000", "+1.55%", "43분"),
            PositionRow("KRW-XRP", "RSI 반등", "3,098", "3,072", "-0.84%", "09분"),
        ],
        signals=[
            SignalRow("KRW-BTC", "5분봉", "EMA20 재돌파 대기", "조건 5 / 6개 충족", 84),
            SignalRow("KRW-ETH", "15분봉", "거래량 증가 확인 중", "조건 4 / 6개 충족", 68),
            SignalRow("KRW-XRP", "5분봉", "과열 해제 대기", "조건 3 / 6개 충족", 47),
        ],
        activities=[
            ActivityRow("09:42", "BTC 진입 예시", "조건 충족 시 이렇게 로그가 남는 형태를 보여줍니다."),
            ActivityRow("09:37", "ETH 보호손절 이동", "수익 구간 진입 후 손절선을 올리는 예시입니다."),
            ActivityRow("09:31", "전략 불러오기", "사용자가 저장한 프로필을 바로 적용하는 흐름입니다."),
            ActivityRow("09:22", "거래소 연결 확인", "API 키 연결 상태를 점검하는 예시 메시지입니다."),
        ],
        exchanges=[
            ExchangeRow("Bybit", "해외거래소 자동매매용 우선 후보", "추천"),
            ExchangeRow("Kraken", "추가 확장 가능한 후보 거래소", "후보"),
            ExchangeRow("맞춤 연동", "원하는 거래소에 맞춰 별도 연결 가능", "옵션"),
        ],
        strategy_fields=[
            StrategyField("1회 매수 금액", 50000, 5000, 500000, 0, " KRW"),
            StrategyField("EMA 근접 허용", 0.25, 0.05, 2.00, 2, " %"),
            StrategyField("거래량 배수", 1.30, 1.00, 5.00, 2, " x"),
            StrategyField("RSI 최소", 52, 30, 70, 0, ""),
            StrategyField("RSI 최대", 68, 40, 90, 0, ""),
            StrategyField("10분 과열 제한", 1.80, 0.50, 8.00, 2, " %"),
        ],
        risk_fields=[
            StrategyField("손절 기준", 1.50, 0.30, 10.00, 2, " %"),
            StrategyField("익절 기준", 2.30, 0.50, 15.00, 2, " %"),
            StrategyField("일 최대 손실", 10000, 5000, 300000, 0, " KRW"),
            StrategyField("최대 동시 보유", 5, 1, 20, 0, "개"),
            StrategyField("손절 후 대기", 10, 0, 180, 0, " 분"),
            StrategyField("재진입 대기", 2, 0, 120, 0, " 분"),
        ],
        market_pulse=[32, 36, 34, 39, 41, 47, 44, 52, 55, 61, 58, 64, 67, 73],
    )
