# Downloads Organizer

파일명을 기준으로 `~/Downloads`의 상위 파일들을 분류하고, 대분류/중분류/묶음 폴더 구조로 이동하는 CLI입니다.

기본 동작은 `dry-run`입니다. 실제 이동은 `--apply`를 줬을 때만 실행합니다.

## 실행

```bash
python3 downloads_organizer.py
```

기본 대상은 `~/Downloads`이고, 결과는 `~/Downloads/_sorted_downloads` 기준으로 계획됩니다.

## 실제 이동

```bash
python3 downloads_organizer.py --apply
```

## 주요 옵션

```bash
python3 downloads_organizer.py \
  --source ~/Downloads \
  --target-root ~/Downloads/_sorted_downloads \
  --config ./organizer_rules.json \
  --similarity-threshold 0.45
```

## 결과물

- `reports/<timestamp>/file_inventory.csv`: 파일 목록과 정규화된 제목
- `reports/<timestamp>/move_plan.csv`: 이동 예정 경로
- `reports/<timestamp>/summary.json`: 카테고리/클러스터 집계

## 분류 방식

1. 파일명을 정규화해서 날짜, 버전, 중복 다운로드 표기 등을 제거합니다.
2. `organizer_rules.json`의 키워드와 확장자로 대분류/중분류를 정합니다.
3. 같은 카테고리 안에서 제목 토큰 유사도로 비슷한 파일끼리 묶습니다.
4. 기본 경로는 `<대분류>/<중분류>/<묶음폴더>/원본파일명`입니다.

필요하면 `organizer_rules.json`에서 키워드를 직접 늘리거나 줄이면 됩니다.
