"""타임폴리오 과거 비중 이력(주간)을 CSV 로 이관한다. 최초 1회만 의미가 있다.

    python scripts/import_legacy.py

data/_legacy/timefolio_weekly.xlsx 를 읽는다.
이 파일은 '행=종목, 열=날짜, 값=비중(%)' 의 가로형이라 날짜별 세로형으로 바꿔 저장한다.

타임폴리오 사이트는 과거 날짜를 제공하지 않아 이 파일이 유일한 과거 이력이다.
2026-01-05 부터 매주 월요일 자료이며, 월요일이 휴장이면 헤더에
'2026-02-16(→2026-02-19)' 처럼 실제 기준일이 화살표 뒤에 적혀 있다.

이미 CSV 가 있는 날짜는 건드리지 않으므로 여러 번 실행해도 안전하다.
"""

from __future__ import annotations

import datetime as dt
import re
import sys

import pandas as pd

from config import DATA_DIR

LEGACY_PATH = DATA_DIR / "_legacy" / "timefolio_weekly.xlsx"
TICKER = "456600"
ARROW = re.compile(r"[→\-–>]+\s*(\d{4}[-.]?\d{2}[-.]?\d{2})\s*\)?\s*$")


def parse_header(value) -> str | None:
    """열 머리글을 YYYYMMDD 로. '2026-02-16(→2026-02-19)' 는 뒤쪽(실제 기준일)을 쓴다."""
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y%m%d")

    text = str(value).strip()
    if not text:
        return None

    m = ARROW.search(text)
    if m:
        text = m.group(1)
    else:
        text = text.split("(")[0].strip()

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) != 8:
        return None
    try:
        dt.datetime.strptime(digits, "%Y%m%d")
    except ValueError:
        return None
    return digits


def main() -> int:
    if not LEGACY_PATH.exists():
        print(f"이관할 파일이 없습니다: {LEGACY_PATH} (건너뜁니다)")
        return 0

    raw = pd.read_excel(LEGACY_PATH, sheet_name=0, header=None)
    header = list(raw.iloc[0].values)

    date_cols: list[tuple[int, str]] = []
    for i, cell in enumerate(header):
        if i < 2:
            continue
        d = parse_header(cell)
        if d:
            date_cols.append((i, d))

    if not date_cols:
        print("[실패] 날짜 열을 찾지 못했습니다. 첫 행을 확인하세요.")
        return 1

    body = raw.iloc[1:].reset_index(drop=True)
    out_dir = DATA_DIR / TICKER
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[이관 시작] {LEGACY_PATH.name} · 날짜 {len(date_cols)}개")
    written = skipped = 0

    for col, date in date_cols:
        target = out_dir / f"{date}.csv"
        if target.exists():
            skipped += 1
            continue

        rows = []
        for _, r in body.iterrows():
            name = str(r.iloc[1]).strip() if len(r) > 1 else ""
            if not name or name.lower() in ("nan", "none") or "합계" in name:
                continue
            weight = pd.to_numeric(r.iloc[col], errors="coerce")
            if pd.isna(weight) or float(weight) == 0:
                continue  # 그 날짜에 편입되지 않은 종목
            code = str(r.iloc[0]).strip()
            if code.lower() in ("nan", "none", ""):
                code = "CASH" if "현금" in name else ""
            rows.append({
                "티커": code,
                "구성종목명": name,
                "계약수": 0,
                "평가금액": 0,
                "비중": round(float(weight), 4),
            })

        if not rows:
            continue

        df = pd.DataFrame(rows)
        df.to_csv(target, index=False, encoding="utf-8-sig")
        written += 1
        print(f"   {date}: {len(df)}종목 (비중합 {df['비중'].sum():.2f}%)")

    print(f"[이관 완료] 신규 {written}일 / 기존 유지 {skipped}일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
