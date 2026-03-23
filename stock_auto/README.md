# stock_auto

미국 정규장 개장 직후 90분 FVG 전략의 Phase 1 백테스트와 브로커 어댑터 골격이다.

## 현재 포함된 기능

- 1분봉 CSV 로드
- 5분봉/15분봉 리샘플링
- opening range + bullish FVG 신호 탐지
- 지정가 진입, 손절, 익절, 11:00 ET 강제청산 시뮬레이션
- Alpaca historical bars 다운로드
- Alpaca paper trading run-once
- 한국투자증권 OpenAPI 해외주식 시세/계좌/주문 run-once
- 거래 요약 통계 출력
- 단위 테스트

## 실행 예시

맥에서 가장 덜 막히는 실행 순서는 이렇다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .

stock-auto --help
```

설치 없이 바로 실행해도 되지만, 맥에서는 아래처럼 `PYTHONPATH=src`를 매번 붙이는 방식보다 `pip install -e .` 후 `stock-auto` 명령을 쓰는 편이 훨씬 안정적이다.

```bash
stock-auto backtest \
  --csv data/sample_spy_minutes.csv \
  --config config/strategy.example.json
```

거래 내역을 별도 CSV로 저장하려면:

```bash
stock-auto backtest \
  --csv data/sample_spy_minutes.csv \
  --config config/strategy.example.json \
  --output-trades data/spy_trades.csv
```

`data/sample_spy_minutes.csv`는 synthetic 예제 데이터다.

실제 SPY 1분봉을 Alpaca에서 내려받으려면:

```bash
export APCA_API_KEY_ID=...
export APCA_API_SECRET_KEY=...

stock-auto fetch-alpaca-bars \
  --symbol SPY \
  --start-date 2026-03-01 \
  --end-date 2026-03-21 \
  --output data/spy_2026-03.csv
```

이 명령은 Alpaca historical bars API를 호출해 `data/spy_2026-03.csv`를 만든다. `end-date`는 exclusive다.

## 한국투자증권 OpenAPI

필수 환경변수:

```bash
export KIS_APP_KEY=...
export KIS_APP_SECRET=...
export KIS_CANO=...
export KIS_ACNT_PRDT_CD=...
export KIS_ENV=demo
```

최근 미국주식 1분봉을 CSV로 저장하려면:

```bash
stock-auto fetch-kis-bars \
  --symbol SPY \
  --quote-exchange AMS \
  --records 180 \
  --output data/spy_kis_recent.csv
```

해외주식 잔고 확인:

```bash
stock-auto kis-balance \
  --country-code 840 \
  --market-code 01
```

미체결 주문 확인:

```bash
stock-auto kis-open-orders \
  --order-exchange NASD
```

오늘 장중 데이터를 기준으로 전략을 평가하고 진입 주문 payload만 만들려면:

```bash
stock-auto kis-run-once \
  --symbol SPY \
  --quote-exchange AMS \
  --order-exchange AMEX \
  --country-code 840 \
  --market-code 05
```

실제 진입 주문까지 내려면 `--submit-entry`를 추가하면 된다.

진입 주문을 실제로 내면 기본적으로 `state/kis_spy_YYYYMMDD.json` 형태의 상태 파일이 생성된다. 경로를 직접 지정하려면 `--state-path`를 쓰면 된다.

저장된 상태 파일을 기준으로 한 번만 모니터링하려면:

```bash
stock-auto kis-monitor-once \
  --state-path state/kis_spy_20260320.json \
  --submit-exit
```

반복 polling으로 자동 청산까지 이어가려면:

```bash
stock-auto kis-monitor-loop \
  --state-path state/kis_spy_20260320.json \
  --poll-seconds 15 \
  --submit-exit
```

모니터는 현재 `REST polling` 기반이며 다음 순서로 동작한다.

- entry 주문 상태 확인
- 포지션 보유 여부 확인
- 현재체결가/1호가 조회
- `stop_hit`, `target_hit`, `session_exit` 중 하나면 매도 지정가 주문 제출
- 포지션이 사라지면 `closed` 상태로 종료

주의:

- Alpaca의 `bracket order`처럼 손절/익절이 브로커에 같이 걸리지 않는다.
- 현재 KIS 청산 자동화는 `REST polling + 상태 파일` 기반이다.
- 실시간 체결통보 WebSocket 기반 모니터는 아직 구현하지 않았다.
- 모의투자 계정은 주문구분 제약이 있어서 미국주식은 사실상 지정가 중심으로 동작한다.

## Telegram

필수 환경변수:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
```

`chat_id`를 아직 모르면 봇과 개인 채팅이나 그룹에서 먼저 한 번 메시지를 보낸 뒤, 아래 명령으로 최근 업데이트를 확인하면 된다.

```bash
stock-auto telegram-get-updates --messages-only --limit 5
```

간단한 테스트 메시지 전송:

```bash
stock-auto telegram-test
```

메시지를 직접 지정하려면:

```bash
stock-auto telegram-test --message "stock_auto test"
```

`TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`가 잡혀 있으면 KIS 실행 경로에서도 텔레그램 알림이 자동으로 전송된다.

- `kis-run-once --submit-entry`: 진입 주문 제출, 진입 불가 상태
- `kis-monitor-once`, `kis-monitor-loop`: 청산 주문 제출, 미체결 진입 취소, 포지션 종료, 충돌 상태, 오류

기본 메시지 헤더는 `[한국투자증권] [미국주식] [심볼]` 형식이다.

## Alpaca Paper Trading

계좌 상태 확인:

```bash
export APCA_API_KEY_ID=...
export APCA_API_SECRET_KEY=...

stock-auto paper-account
```

열린 주문 확인:

```bash
stock-auto paper-list-orders --status open
```

오늘 장중 데이터를 다시 받아 전략을 평가하고 bracket order를 준비만 하려면:

```bash
stock-auto paper-run-once \
  --symbol SPY \
  --config config/strategy.example.json \
  --dry-run
```

실제 paper order 제출까지 하려면 `--dry-run`을 빼면 된다.

## 입력 CSV 형식

필수 컬럼:

- `timestamp`
- `open`
- `high`
- `low`
- `close`

선택 컬럼:

- `volume`
- `symbol`

`timestamp`는 ISO-8601 문자열을 권장한다.

- timezone 포함: `2026-03-20T09:30:00-04:00`
- timezone 미포함: `--data-timezone` 값 기준으로 해석

## 기본 전략 요약

- 종목: `SPY`
- opening range: 정규장 첫 `15분봉`
- 신호: `ORH` 몸통 돌파 이후 `bullish FVG`
- 진입: `FVG 상단 첫 터치`
- 손절: `FVG A봉 저점`
- 익절: `2R`
- 강제 종료: `11:00 ET`

자세한 설계는 [docs/us-opening-fvg-bot-design.md](/Users/jeongnis-si/workspace_test/stock_auto/docs/us-opening-fvg-bot-design.md)에 정리되어 있다.
