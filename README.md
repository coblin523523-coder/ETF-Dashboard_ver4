# 글로벌 AI ETF 구성종목 대시보드

ETF 3종의 구성종목을 **각 운용사 공시에서 매일 받아** 전일 대비 편입·편출·비중 증감을
보여주는 정적 대시보드입니다. PC를 켜둘 필요 없이 GitHub Actions가 대신 돌립니다.

| 코드 | ETF | 데이터 출처 | 과거 소급 |
|---|---|---|---|
| 456600 | TIMEFOLIO 글로벌AI인공지능액티브 | timeetf.co.kr | 불가 (첨부 엑셀로 대체) |
| 471040 | KoAct 글로벌AI&로봇액티브 | samsungactive.co.kr | 가능 (`gijunYMD`) |
| 466950 | TIGER 글로벌AI액티브 | investments.miraeasset.com | 가능 (`fixDate`) |

## 왜 KRX(pykrx)를 안 쓰나

처음에는 pykrx로 KRX 공시 PDF를 받으려 했지만 두 가지 벽에 막혔습니다.

1. KRX 정보데이터시스템이 2025년 12월부터 **회원제로 전환**되어 비로그인 요청을 거부합니다.
2. 로그인해도 **해외 편입 종목의 금액·비중을 0으로** 줍니다. 이 3종은 해외 자산이 주력이라
   456600 기준 42종목 중 금액이 있는 건 2종목뿐이었습니다.

운용사는 비중을 그대로 공시하므로 훨씬 정확하고, 환산 로직도 필요 없습니다.

## 구조

```
scripts/config.py         ETF 정의 (출처·파라미터·소급 지원 여부)
scripts/sources.py        운용사별 수집기 3종
scripts/collect.py        수집 오케스트레이터
scripts/import_legacy.py  타임폴리오 과거 주간 엑셀 -> CSV (최초 1회)
scripts/payload.py        TOP10·편출입·추이 집계
scripts/render.py         docs/index.html 생성
data/<티커>/YYYYMMDD.csv  날짜별 구성종목 = 이력 그 자체
data/_legacy/             타임폴리오 과거 엑셀 원본
docs/index.html           대시보드 (GitHub Pages가 서빙)
```

## 설치

1. **Public 저장소**에 이 파일들을 업로드
2. `Settings → Actions → General` → **Read and write permissions** → Save
3. `Settings → Pages` → Branch `main`, 폴더 `/docs` → Save
4. `Actions` → `일별 ETF 구성종목 수집` → **Run workflow** (backfill `250`)

KRX 계정도, 어떤 Secrets도 필요 없습니다.

## 첫 실행 때 일어나는 일

- `과거 이력 이관` — `data/_legacy/timefolio_weekly.xlsx` 의 주간 이력 33일치를
  `data/456600/` 에 CSV로 풀어 놓습니다. 이미 있는 날짜는 건드리지 않습니다.
- `구성종목 수집` — 미래에셋·삼성액티브는 250영업일 소급, 타임폴리오는 오늘치만.
- `대시보드 생성` → `변경분 커밋` → Pages 자동 반영.

## 자동 실행

매주 월~금 **07:00 KST** (`cron: "0 22 * * 0-4"`, UTC 기준). 버튼을 누를 필요 없습니다.
스케줄 실행은 `--backfill 5` 로 돌아 최근 5영업일 중 빠진 날을 스스로 메꿉니다.

시간을 바꾸려면 `.github/workflows/daily.yml` 의 cron에서 **한국시간 -9시간**을 넣으세요.

## 알아둘 점

- **타임폴리오 과거는 주간 단위입니다.** 2026-01-05 ~ 08-17 은 매주 월요일 자료라
  그 구간의 '전일 대비'는 사실상 '전주 대비'입니다. 오늘부터는 매일 쌓입니다.
- **휴장일 방어** — 직전 저장분과 구성·비중이 완전히 같으면 저장하지 않습니다.
  타임폴리오처럼 날짜 파라미터가 없는 곳에서 같은 데이터가 중복 저장되는 걸 막습니다.
- **수집 실패는 조용히 넘어갑니다.** 한 ETF가 실패해도 나머지는 정상 갱신되고,
  다음 실행에서 빠진 날짜를 다시 시도합니다.
- Actions cron은 저장소 활동이 60일간 없으면 정지되지만, 이 워크플로가 매일 커밋하므로
  스스로 활동을 만들어 문제되지 않습니다.

## 면책

각 운용사 공시 자료를 가공한 정보 제공용 페이지입니다. 투자 판단의 근거로 삼기 전에
반드시 운용사 원 공시를 확인하세요.
