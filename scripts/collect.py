"""ETF 구성종목을 운용사 공시에서 받아 data/ 에 날짜별 CSV로 누적한다.

    python scripts/collect.py                 # 오늘(KST) 기준 수집
    python scripts/collect.py --date 20260814 # 특정일 수집
    python scripts/collect.py --backfill 250  # 과거 250 영업일 소급 (지원 ETF만)

소급 가능 여부는 ETF마다 다르다. config.ETFS 의 backfill 값을 따른다.
타임폴리오는 사이트가 과거를 제공하지 않아 오늘치만 받는다.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from config import DATA_DIR, ETFS
from sources import fetch

KST = ZoneInfo("Asia/Seoul")
SLEEP = 0.4  # 운용사 서버 배려


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def business_days_back(end: str, count: int) -> list[str]:
    """end 부터 과거로 주말을 뺀 날짜 목록. 공휴일은 응답이 비어 자연히 걸러진다."""
    days, cursor = [], datetime.strptime(end, "%Y%m%d")
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.strftime("%Y%m%d"))
        cursor -= timedelta(days=1)
    return days


def latest_saved(ticker: str) -> tuple[str, pd.DataFrame] | None:
    d = DATA_DIR / ticker
    files = sorted(d.glob("*.csv")) if d.exists() else []
    if not files:
        return None
    return files[-1].stem, pd.read_csv(files[-1], dtype={"티커": str})


def same_holdings(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """비중까지 완전히 같은지. 휴장일에 전일 데이터가 그대로 오는 경우를 걸러낸다."""
    if a is None or b is None or len(a) != len(b):
        return False
    ka = sorted(zip(a["구성종목명"].astype(str), a["비중"].round(4)))
    kb = sorted(zip(b["구성종목명"].astype(str), b["비중"].round(4)))
    return ka == kb


def save(ticker: str, date: str, df: pd.DataFrame) -> None:
    out = DATA_DIR / ticker
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"{date}.csv", index=False, encoding="utf-8-sig")


def collect_etf(etf: dict, dates: list[str], force: bool) -> int:
    ticker, name = etf["ticker"], etf["name"]
    print(f"\n── {name} ({ticker}) · {etf['source']}")

    if not etf.get("backfill", False):
        # 사이트가 과거를 안 주므로 오늘치만 의미가 있다
        dates = dates[:1]
        print("   과거 조회 미지원 → 최신일만 수집")

    saved = 0
    errors: dict[str, int] = {}
    streak = 0          # 연속 실패 횟수
    ABORT_AFTER = 5     # 같은 오류가 이만큼 이어지면 이 ETF는 포기한다
    for date in dates:
        target = DATA_DIR / ticker / f"{date}.csv"
        if target.exists() and not force:
            continue

        try:
            df = fetch(etf, date)
        except Exception as exc:
            key = f"{type(exc).__name__}: {str(exc)[:90]}"
            errors[key] = errors.get(key, 0) + 1
            if errors[key] <= 2:          # 같은 오류는 두 번까지만 자세히
                print(f"   {date}: 실패 {key}")
            streak += 1
            if streak >= ABORT_AFTER:
                print(f"   연속 {streak}회 실패 → 남은 {len(dates) - dates.index(date) - 1}일은 "
                      f"시도하지 않습니다 (사이트 접근 불가로 판단)")
                break
            continue

        streak = 0
        if df is None or df.empty:
            continue

        # 휴장일에 직전 영업일 데이터가 그대로 오는 경우를 방지
        prev = latest_saved(ticker)
        if prev and prev[0] != date and same_holdings(df, prev[1]):
            print(f"   {date}: {prev[0]} 과 내용 동일 → 휴장일로 보고 건너뜀")
            continue

        save(ticker, date, df)
        total = df["비중"].sum()
        print(f"   {date}: {len(df)}종목 저장 (비중합 {total:.2f}%)")
        saved += 1
        time.sleep(SLEEP)

    for key, n in errors.items():
        if n > 2:
            print(f"   (동일 오류 {n}회 반복) {key}")
    if saved == 0:
        print("   신규 저장 없음 (이미 있거나 데이터 미제공)")
    return saved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="기준일 YYYYMMDD (기본: 오늘 KST)")
    ap.add_argument("--backfill", type=int, default=0, help="과거 N 영업일 소급")
    ap.add_argument("--force", action="store_true", help="이미 있는 날도 다시 받기")
    ap.add_argument("--only", help="특정 티커만 수집")
    args = ap.parse_args()

    end = args.date or today_kst()
    dates = business_days_back(end, args.backfill) if args.backfill > 0 else [end]

    print(f"[수집 시작] 기준일 {end} / 대상 {len(dates)}일 / "
          f"{datetime.now(KST):%Y-%m-%d %H:%M:%S} KST")

    total = 0
    for etf in ETFS:
        if args.only and etf["ticker"] != args.only:
            continue
        total += collect_etf(etf, dates, args.force)

    print(f"\n[수집 완료] 신규 저장 {total}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
