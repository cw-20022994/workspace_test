# Coin Partner

업비트 현물 자동매매용 개인 봇입니다. 이 문서는 사람뿐 아니라 다른 AI가 읽어도 바로 실행 흐름과 현재 전략 상태를 이해할 수 있도록 정리돼 있습니다.

## AI Quick Start

이 프로젝트를 이어서 작업하는 AI는 아래 순서로 보면 됩니다.

1. 현재 실행 프로필이 무엇인지 확인합니다.
2. 비밀정보와 상태 파일은 Git에 없다는 점을 확인합니다.
3. 운영체제에 맞는 실행 방법을 사용합니다.
4. 실거래 상태를 건드릴 때는 `data/state.json`과 업비트 실제 잔고 동기화를 먼저 확인합니다.

핵심 파일:

- 엔트리포인트: `src/coin_partner/cli.py`
- 메인 루프: `src/coin_partner/bot.py`
- 전략: `src/coin_partner/strategy.py`
- 리스크: `src/coin_partner/risk.py`
- 거래소 연동: `src/coin_partner/upbit.py`
- 상태 저장: `src/coin_partner/state.py`
- 알림: `src/coin_partner/telegram.py`

## Runtime Profiles

- `config.example.toml`
  `paper` 모드 예시 설정
- `config.live-manage.toml`
  실포지션만 관리하고 새 진입은 막는 설정
- `config.live-auto.toml`
  현재 실거래 자동 진입 설정

현재 대화 기준 실운용 프로필은 `config.live-auto.toml`입니다.

## Security And Local State

Git에 올라가지 않는 파일:

- `config.toml`
- `data/state.json`
- `data/*.log`
- `data/*.pid`

즉, GitHub만 내려받아서는 실거래 상태가 복원되지 않습니다. 아래 항목은 로컬에서 다시 준비해야 합니다.

- `UPBIT_ACCESS_KEY`
- `UPBIT_SECRET_KEY`
- `TELEGRAM_BOT_TOKEN`
- 필요 시 로컬 `config.toml`
- 필요 시 기존 `data/state.json`

## Current Live Strategy

현재 `config.live-auto.toml` 기준 규칙은 아래와 같습니다.

### 자금/리스크

- 총 운용 한도: `200,000 KRW`
- 1회 진입금액: `50,000 KRW`
- 일 최대 손실: `10,000 KRW`
- 하루 최대 거래 횟수 제한: `없음`
- 연속 손절 중단: `없음`
- 손절 후 전역 쿨다운: `10분`
- 익절 후 전역 쿨다운: `없음`
- 같은 마켓 재진입 쿨다운: `2분`
- `max_open_positions = 10`이지만 실제 진입 수는 총 자금 한도와 `min_krw_balance_buffer = 10,000 KRW` 때문에 먼저 제한됩니다

### 진입 규칙

진입 판단은 `완성된 5분봉` 기준입니다.

- 시장: `KRW-BTC`, `KRW-ETH`
- 최근 완성 5분봉 저가가 `5분 EMA20` 근처까지 눌림
- 최근 완성 5분봉 종가가 `5분 EMA20` 위로 회복
- 최근 완성 5분봉 종가가 직전 5분봉 고가 돌파
- 거래량이 최근 20개 5분봉 평균의 `1.3배` 이상
- `RSI(14)`가 `52~68`
- RSI가 직전 봉보다 상승
- 최근 10분 상승률이 `1.8%` 이상이면 진입 금지

1시간 추세 필터:

- `KRW-BTC`
  완화 적용
  `현재가 > 1시간 EMA20` 이고 `1시간 EMA20이 최근 2개 봉 연속 상승`
- `KRW-ETH`
  보수적 유지
  `1시간 EMA20 > EMA50` 이고 `현재가 > 1시간 EMA20`

### 청산 규칙

- 손절: `-1.5%`
- 익절: `+2.3%`
- 수익이 `+1.4%`를 넘으면 보호 손절선을 `-0.2%` 수준으로 상향
- 시간 청산: 진입 후 `60분`
- 청산 판단은 현재 `1분` 루프 기준

## macOS / zsh Quick Start

### 1. 예시 설정 복사

```bash
cp config.example.toml config.toml
```

### 2. 종이매매 1회 실행

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --once
```

### 3. 상태 확인

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --status
```

### 4. 실거래 자동모드 1회 실행

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.live-auto.toml --once
```

### 5. 백그라운드 서비스 실행

이 스크립트는 `~/.coin_partner_env`를 읽습니다.

```bash
./scripts/live_auto_service.sh start
./scripts/live_auto_service.sh status
tail -f data/live_auto.log
```

중지:

```bash
./scripts/live_auto_service.sh stop
```

## Windows / PowerShell Quick Start

Windows에서도 Python 본체는 그대로 동작합니다. 다만 현재 `scripts/*.sh`는 macOS/zsh 기준이라 Windows에서는 직접 Python 명령으로 실행하는 것이 기본입니다.

### 1. 예시 설정 복사

```powershell
Copy-Item config.example.toml config.toml
```

### 2. 환경변수 설정

```powershell
$env:UPBIT_ACCESS_KEY = "..."
$env:UPBIT_SECRET_KEY = "..."
$env:TELEGRAM_BOT_TOKEN = "..."
$env:PYTHONPATH = "src"
```

### 3. 종이매매 1회 실행

```powershell
python -m coin_partner.cli --config config.toml --once
```

### 4. 실거래 자동모드 1회 실행

```powershell
python -m coin_partner.cli --config config.live-auto.toml --once
```

### 5. 반복 실행

```powershell
python -m coin_partner.cli --config config.live-auto.toml
```

주의:

- macOS의 `live_auto_service.sh`에 대응하는 Windows 서비스 스크립트는 아직 없습니다.
- Windows에서는 `PowerShell`, `작업 스케줄러`, 또는 별도 서비스 래퍼로 운영해야 합니다.

## Upbit Live Connection Checklist

실거래 연결은 아래 순서가 안전합니다.

1. 업비트에서 API Key 발급
2. 먼저 `자산조회` 권한만으로 연결 확인
3. 허용 IP 등록
4. 이후 `주문하기` 권한이 있는 별도 Key 사용
5. 처음엔 `수동 1회 주문`이나 `manage-only` 모드로 확인

읽기 전용 확인:

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --check-upbit
```

Windows:

```powershell
$env:UPBIT_ACCESS_KEY = "..."
$env:UPBIT_SECRET_KEY = "..."
$env:PYTHONPATH = "src"
python -m coin_partner.cli --config config.toml --check-upbit
```

## Manual Live Smoke Test

macOS/zsh:

```bash
export UPBIT_ACCESS_KEY="..."
export UPBIT_SECRET_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml \
  --manual-buy-market KRW-BTC \
  --manual-buy-krw 10000 \
  --live-order-confirm "BUY:KRW-BTC:10000"
```

Windows/PowerShell:

```powershell
$env:UPBIT_ACCESS_KEY = "..."
$env:UPBIT_SECRET_KEY = "..."
$env:TELEGRAM_BOT_TOKEN = "..."
$env:PYTHONPATH = "src"
python -m coin_partner.cli --config config.toml --manual-buy-market KRW-BTC --manual-buy-krw 10000 --live-order-confirm "BUY:KRW-BTC:10000"
```

수동 주문 후에는 로컬 상태에 import 해야 합니다.

```bash
PYTHONPATH=src python3 -m coin_partner.cli --config config.toml --import-order-id <UPBIT_ORDER_UUID>
```

```powershell
python -m coin_partner.cli --config config.toml --import-order-id <UPBIT_ORDER_UUID>
```

## Telegram Notifications

텔레그램 알림은 아래 상황에서 전송됩니다.

- 진입 체결
- 청산 체결
- 당일 거래 중단
- 일일 마감 요약
- 하트비트
- 오류

필수값:

- `TELEGRAM_BOT_TOKEN`
- `chat_id`

설정 예시는 `config.example.toml`의 `[telegram]` 섹션에 있습니다.

## Known Limitations

- `data/state.json`과 실제 업비트 계정이 어긋나면 먼저 동기화가 필요합니다.
- 외부에서 같은 계정으로 수동 거래하면 봇 상태가 틀어질 수 있습니다.
- macOS 서비스 스크립트는 현재 `zsh` 기준입니다.
- Windows용 서비스 스크립트는 아직 없습니다.
- 맥북이 잠자기에 들어가면 로컬 실행 봇은 사실상 멈춥니다.

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
