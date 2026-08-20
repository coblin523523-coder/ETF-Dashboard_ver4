"""대시보드 공통 설정.

데이터는 KRX가 아니라 각 운용사 공시에서 직접 받는다.
KRX PDF는 해외 편입 종목의 금액·비중을 0으로 주기 때문에 쓸 수 없었다.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

# 추적 대상 ETF. 순서가 대시보드 탭 순서가 된다.
# source 는 sources.py 의 수집 함수를 고른다.
ETFS = [
    {
        "ticker": "456600",
        "name": "TIMEFOLIO 글로벌AI인공지능액티브",
        "short": "TIMEFOLIO AI",
        # 탭·배지는 항상 브랜드색 바탕에 흰 글자다.
        # base=평소 바탕, solid=선택됐을 때 바탕(더 진하게)
        "color": {"base": "#2a4a7c", "solid": "#14305c"},
        "source": "timefolio",
        "params": {"cate": "001", "idx": "6"},
        # 사이트가 과거 날짜를 제공하지 않는다. 오늘치만 받아 누적한다.
        "backfill": False,
    },
    {
        "ticker": "471040",
        "name": "KoAct 글로벌AI&로봇액티브",
        "short": "KoAct AI·로봇",
        "color": {"base": "#2470c9", "solid": "#14539f"},
        "source": "samsung",
        "params": {"fund_id": "2ETFL3"},
        "backfill": True,
    },
    {
        "ticker": "466950",
        "name": "TIGER 글로벌AI액티브",
        "short": "TIGER AI",
        "color": {"base": "#c44d1a", "solid": "#8f3609"},
        "source": "mirae",
        "params": {"ksd_fund": "KR7466950003"},
        # 미래에셋은 해외 데이터센터 IP를 방화벽에서 막는다(홈페이지조차 403).
        # 그래서 GitHub 서버에서는 수집이 불가능하고, 이력은 data/_legacy 의
        # 엑셀에서 가져온다. 차단이 풀릴 수도 있으니 최신일 하루만 찔러본다.
        "backfill": False,
        "note": "미래에셋이 서버 IP를 차단 중 · 이력은 주기적 엑셀 갱신으로 보충",
    },
]

TOP_N = 10
SPARK_DAYS = 20

# 저장 CSV 컬럼. 운용사는 비중을 직접 주므로 환산이 필요 없다.
# 계약수·평가금액은 제공되는 경우에만 채워지고, 없으면 0으로 둔다.
CSV_COLUMNS = ["티커", "구성종목명", "계약수", "평가금액", "비중"]


def etf_by_ticker(ticker: str) -> dict | None:
    return next((e for e in ETFS if e["ticker"] == ticker), None)
