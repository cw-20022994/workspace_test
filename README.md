# workspace_test

개인 자동화/투자/리포트 작업을 모아둔 모노레포입니다.

## AI Quick Start

다른 AI가 이 저장소를 이어서 작업할 때는 아래 순서로 보면 됩니다.

1. 먼저 이 파일을 읽습니다.
2. 현재 활성 프로젝트가 무엇인지 확인합니다.
3. 해당 프로젝트의 README를 읽습니다.
4. 비밀정보와 런타임 상태 파일은 Git에 없다는 점을 전제로 작업합니다.

현재 이 저장소에서 가장 최근에 적극적으로 작업한 프로젝트는 `coin_partner`입니다.

## Project Map

- `accounting/`: 간단한 지출 요약 스크립트
- `coin_partner/`: 업비트 현물 자동매매 봇
- `file_store/`: 다운로드 파일 정리 도구
- `stock_auto/`: 주식 자동매매/백테스트 실험 코드
- `stock_report/`: 주식 리포트 생성 파이프라인

## Security And Runtime State

이 저장소에는 아래 항목이 올라가지 않도록 설정되어 있습니다.

- 로컬 비밀키/환경파일
- 런타임 상태 파일
- 로그 파일
- 생성 리포트와 캐시

예:

- `coin_partner/config.toml`
- `coin_partner/data/state.json`
- `stock_report/config/runtime.env`
- `file_store/reports/`

즉, GitHub에 있는 내용만으로는 바로 실거래 상태가 복원되지 않습니다. 실행하려면 각 프로젝트에서 로컬 환경변수나 무시된 설정 파일을 다시 만들어야 합니다.

## Platform Notes

- `macOS`: 일부 프로젝트는 `scripts/*.sh`를 바로 사용할 수 있습니다.
- `Windows`: Python 엔트리포인트는 그대로 사용할 수 있지만, `.sh` 스크립트는 `PowerShell` 명령으로 바꿔서 실행해야 합니다.

`coin_partner`는 두 운영체제 모두 실행 가능하지만, 서비스 관리 스크립트는 현재 `macOS/zsh` 기준입니다. Windows에서는 `python -m ...` 방식으로 직접 실행하는 것이 기본입니다.

## Recommended Entry Point

`coin_partner`를 작업하려면 아래 문서를 먼저 읽으면 됩니다.

- [coin_partner/README.md](/Users/jeongnis-si/workspace_test/coin_partner/README.md)

그 문서에는 아래가 정리돼 있습니다.

- 현재 전략 규칙
- macOS 실행 방법
- Windows 실행 방법
- 라이브 운용 시 주의사항
- 상태 파일과 환경변수 구조
