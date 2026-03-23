# Coin Partner

업비트 현물 자동매매용 개인 봇입니다. 첫 버전은 `paper` 모드가 기본이며, 사용자가 합의한 규칙만 고정해 둔 상태로 시작합니다.

핵심 규칙:

- 현물만 사용
- 시장: `KRW-BTC`, `KRW-ETH`
- 1회 진입금액: `30,000 KRW`
- 동시 포지션: `1개`
- 하루 최대 거래: `5회`
- 하루 최대 손실: `7,000 KRW`
- 손절: `-1.5%`
- 익절: `+2.3%`
- `+1.4%` 도달 시 손절선을 `-0.2%`로 상향
- 최대 보유 시간: `60분`
- 손절 후 `10분` 쿨다운

## 실행 전제

- Python `3.9+`
- 업비트 실거래를 켜려면 본인 API 키가 필요합니다.
- 기본 모드는 `paper`라서 키 없이 실행됩니다.
- 텔레그램 알림을 쓰려면 BotFather에서 발급한 봇 토큰과 본인 `chat_id`가 필요합니다.

## 시작 방법

1. 예시 설정을 복사합니다.

```bash
cp config.example.toml config.toml
```

2. 한 번만 실행해 상태를 확인합니다.

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --once
```

3. 상태를 출력합니다.

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --status
```

4. 반복 실행합니다.

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml
```

## 업비트 실제 연결 순서

실거래 연결은 아래 순서로 진행하는 것이 안전합니다.

1. 업비트에서 API Key를 발급합니다.
2. 첫 연결 테스트용 Key는 `자산조회` 권한만 켭니다.
3. `주문하기`, `입출금`, `출금` 관련 권한은 처음에는 끕니다.
4. 호출할 PC 또는 서버의 `공인 IP`를 허용 IP에 등록합니다.
5. 환경변수로 Key를 넣고 읽기 전용 연결만 확인합니다.

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --check-upbit
```

연결 확인이 끝난 뒤에만 `주문하기` 권한을 추가한 별도 Key로 실거래 전환을 검토하세요.

## 1회 실거래 스모크 테스트

실제 주문을 1회만 넣고 싶다면 아래처럼 `수동 1회 시장가 매수` 커맨드를 사용할 수 있습니다.

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml \
  --manual-buy-market KRW-BTC \
  --manual-buy-krw 10000 \
  --live-order-confirm "BUY:KRW-BTC:10000"
```

같은 작업을 숨김 입력으로 바로 실행하려면:

```bash
./scripts/manual_live_buy.sh KRW-BTC 10000
```

수동 주문 후에는 자동매매 상태와 실제 보유 포지션이 어긋날 수 있으므로, 주문 UUID를 로컬 상태에 가져와야 합니다.

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml \
  --import-order-id a5072f84-7e99-4d80-93f6-a699f6a3ea7d
```

이 명령은 주문 조회 후, 체결된 매수 주문을 현재 오픈 포지션으로 `data/state.json`에 기록합니다.

실포지션만 관리하고 새 진입은 막으려면 `config.toml`을 아래처럼 바꾸세요.

```toml
[bot]
mode = "live"
allow_new_entries = false
```

주의:

- 이 명령은 `실제 주문`입니다.
- `주문하기` 권한이 있는 API Key여야 합니다.
- 확인 문자열이 정확히 맞지 않으면 주문이 차단됩니다.

## 실거래 전환

`config.toml`에서 아래를 수정합니다.

```toml
[bot]
mode = "live"
allow_new_entries = true
```

그 다음 환경변수로 API 키를 주입합니다.

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
```

주의:

- 실거래는 로컬 상태 파일을 기준으로 리스크 제한과 포지션을 추적합니다.
- 다른 곳에서 같은 계정으로 수동 거래하면 상태가 어긋날 수 있습니다.
- 첫 실거래 전에는 반드시 `paper` 모드로 충분히 검증하세요.
- 수동으로 잡은 실포지션 청산만 맡기려면 `mode = "live"`와 `allow_new_entries = false`를 같이 사용하세요.
- `bot.live_capital_limit_krw`로 라이브 계좌에서 봇이 사용할 최대 자금을 제한할 수 있습니다. 현재 `config.live-auto.toml`은 `총 200,000 KRW 한도`, `1회 50,000 KRW 진입`, `BTC만 1시간 추세 필터 완화`, `최대 보유 60분`으로 설정되어 있습니다.
- 현재는 여러 포지션을 독립 lot처럼 관리합니다. 그래서 BTC 보유 중에도 ETH 진입이 가능하고, 같은 코인도 새 신호가 나오면 추가 lot 진입이 가능합니다.
- `max_open_positions`는 현재 `10`으로 넉넉하게 열어뒀지만, 실제 진입 수는 `총 운용 한도`와 `min_krw_balance_buffer`에 의해 먼저 제한됩니다. 지금 설정에서는 사실상 `총 20만원` 범위 안에서만 늘어납니다.
- `max_trades_per_day = 0`, `max_consecutive_stop_losses = 0`은 비활성화 의미입니다. 대신 `daily_loss_limit_krw = 10000`이 당일 손실 한도 역할을 합니다.
- 익절 직후 전역 쿨다운은 없고, 같은 마켓만 `2분` 재진입 쿨다운을 둡니다.

자동 진입까지 열고 `1회 50,000 KRW`씩 거래하려면:

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.live-auto.toml --once
```

계속 실행:

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.live-auto.toml
```

터미널을 닫아도 자동 진입 모드로 계속 돌리려면:

```bash
./scripts/live_auto_service.sh start
```

터미널을 닫아도 계속 돌리려면:

```bash
./scripts/live_manage_service.sh start
```

상태 확인:

```bash
./scripts/live_manage_service.sh status
```

로그 보기:

```bash
./scripts/live_manage_service.sh logs
```

중지:

```bash
./scripts/live_manage_service.sh stop
```

주의:

- 이 스크립트는 `~/.coin_partner_env`를 자동으로 읽습니다.
- 맥북이 잠자기에 들어가면 봇도 사실상 멈춥니다.
- 상시 운용은 절전 해제 또는 별도 서버가 필요합니다.

## 텔레그램 알림

기본 설정은 꺼져 있습니다. `config.toml`의 `[telegram]` 섹션을 켜고, 환경변수로 봇 토큰을 넣으면 됩니다.

```toml
[telegram]
enabled = true
bot_token_env = "TELEGRAM_BOT_TOKEN"
chat_id = "123456789"
parse_mode = "HTML"
send_silently = false
request_timeout_seconds = 10
notify_entry = true
notify_exit = true
notify_daily_stop = true
notify_daily_summary = true
daily_summary_hour = 23
daily_summary_minute = 0
notify_heartbeat = true
heartbeat_interval_minutes = 60
notify_errors = true
error_cooldown_minutes = 15
```

```bash
export TELEGRAM_BOT_TOKEN="..."
```

설정 순서:

1. `@BotFather`에서 봇을 만들고 토큰을 받습니다.
2. 텔레그램 앱에서 봇과 대화를 시작합니다.
3. 봇에게 아무 메시지나 하나 보냅니다.
4. 아래 호출로 `chat.id`를 확인합니다.

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

알림은 아래 상황에서 전송됩니다.

- 진입 체결
- 청산 체결
- 당일 손실 한도 또는 연속 손절로 거래 중단
- 일일 마감 요약
- 생존 확인 하트비트
- 업비트 API 오류 또는 런타임 오류

진입 알림에는 시장, 진입가, 수량, 손절가, 익절가가 포함됩니다. 청산 알림에는 청산 사유, 손익 금액, 손익률, 당일 누적 손익이 포함됩니다.
일일 마감 요약에는 당일 손익, 거래 횟수, 승/패, 최고/최저 손익이 포함됩니다.
하트비트에는 현재 시각, 당일 손익, 거래 횟수, 현금 상태, 보유 포지션과 미실현 손익이 포함됩니다.

## 전략 요약

진입 조건은 완성된 5분봉 기준입니다.

- 1시간봉 `EMA20 > EMA50`
- 현재가가 1시간봉 `EMA20` 위
- 최근 완성 5분봉 저가가 5분봉 `EMA20` 근처까지 눌렸다가 회복
- 최근 완성 5분봉 종가가 직전 5분봉 고가 돌파
- 거래량이 직전 20개 5분봉 평균의 `1.3배` 이상
- `RSI(14)`가 `52~68` 사이이면서 직전 봉보다 상승
- 최근 10분 누적 상승률이 `1.8%` 이상이면 진입 금지

청산은 실시간 현재가를 기준으로 수행합니다.

- `-1.5%` 손절
- `+2.3%` 익절
- `+1.4%` 이상 이익이면 보호 손절선을 `-0.2%`로 상향
- 진입 후 `60분`이 지나면 시간 청산

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## 참고한 공식 문서

- Upbit API 개요: https://docs.upbit.com/kr/reference/api-overview
- Upbit 인증: https://docs.upbit.com/kr/reference/auth
- Upbit 분봉 조회: https://docs.upbit.com/kr/reference/list-candles-minutes
- Upbit 주문 생성: https://docs.upbit.com/kr/reference/new-order
- Upbit 계정 잔고 조회: https://docs.upbit.com/kr/reference/get-balance
- Upbit KRW 최소 주문금액: https://docs.upbit.com/kr/kr/docs/krw-market-info
- Telegram bot 소개: https://core.telegram.org/bots
- Telegram Bot API `sendMessage`: https://core.telegram.org/bots/api#sendmessage
