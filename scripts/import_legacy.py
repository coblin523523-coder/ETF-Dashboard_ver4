"""운용사 사이트에서 못 받는 과거 이력을 엑셀에서 CSV 로 이관한다.

    python scripts/import_legacy.py

data/_legacy/ 안의 모든 .xlsx 를 읽는다. 파일명 앞의 6자리 숫자가 대상 ETF 티커다.
    예) 466950_tiger_daily.xlsx  ->  data/466950/*.csv

엑셀 모양이 두 가지라 둘 다 처리한다.

  가로형 : 행=종목, 열=날짜, 값=비중(%)          (타임폴리오 주간 자료)
           열 머리글이 '2026-02-16(→2026-02-19)' 이면 화살표 뒤를 실제 기준일로 쓴다.
  세로형 : 기준일·종목코드·종목명·수량·평가금액·비중 컬럼      (TIGER 일간 자료)

이미 CSV 가 있는 날짜는 건드리지 않으므로 여러 번 실행해도 안전하다.
"""

from __future__ import annotations

import datetime as dt
import re
import sys

import pandas as pd

from config import DATA_DIR

LEGACY_DIR = DATA_DIR / "_legacy"
ARROW = re.compile(r"[→\-–>]+\s*(\d{4}[-.]?\d{2}[-.]?\d{2})\s*\)?\s*$")

# 티커가 파일명에 없는 예전 파일 이름은 여기서 이어준다
FALLBACK_TICKER = {"timefolio_weekly.xlsx": "456600"}


def parse_date(value) -> str | None:
    """다양한 표기의 날짜를 YYYYMMDD 로. 실패하면 None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y%m%d")

    text = str(value).strip()
    if not text:
        return None
    m = ARROW.search(text)
    text = m.group(1) if m else text.split("(")[0].strip()

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) != 8:
        return None
    try:
        dt.datetime.strptime(digits, "%Y%m%d")
    except ValueError:
        return None
    return digits


def ticker_of(path) -> str | None:
    m = re.match(r"(\d{6})", path.name)
    if m:
        return m.group(1)
    return FALLBACK_TICKER.get(path.name)


def _num(x) -> float:
    v = pd.to_numeric(str(x).replace(",", "").replace("%", ""), errors="coerce")
    return 0.0 if pd.isna(v) else float(v)


def read_long(raw: pd.DataFrame) -> dict[str, list[dict]] | None:
    """세로형(기준일 컬럼이 있는 형태)을 날짜별 레코드로."""
    header_row = None
    for r in range(min(len(raw), 15)):
        cells = [str(c) for c in raw.iloc[r].values]
        if any("기준일" in c for c in cells) and any("비중" in c for c in cells):
            header_row = r
            break
    if header_row is None:
        return None

    cols = [str(c).strip() for c in raw.iloc[header_row].values]

    def find(*kws):
        for i, c in enumerate(cols):
            if any(k in c for k in kws):
                return i
        return None

    i_date, i_rate = find("기준일"), find("비중")
    i_code, i_name = find("종목코드", "코드"), find("종목명")
    i_qty, i_amt = find("수량", "계약수"), find("평가금액", "금액")
    if i_date is None or i_rate is None or i_name is None:
        return None

    out: dict[str, list[dict]] = {}
    for _, row in raw.iloc[header_row + 1:].iterrows():
        vals = list(row.values)
        date = parse_date(vals[i_date]) if i_date < len(vals) else None
        if not date:
            continue
        name = str(vals[i_name]).strip() if i_name < len(vals) else ""
        if not name or name.lower() in ("nan", "none") or "합계" in name:
            continue
        rate = _num(vals[i_rate]) if i_rate < len(vals) else 0.0
        if rate == 0:
            continue
        code = str(vals[i_code]).strip() if i_code is not None and i_code < len(vals) else ""
        if code.lower() in ("nan", "none"):
            code = ""
        if not code and "현금" in name:
            code = "CASH"
        out.setdefault(date, []).append({
            "티커": code,
            "구성종목명": name,
            "계약수": _num(vals[i_qty]) if i_qty is not None and i_qty < len(vals) else 0,
            "평가금액": _num(vals[i_amt]) if i_amt is not None and i_amt < len(vals) else 0,
            "비중": round(rate, 4),
        })
    return out or None


def read_wide(raw: pd.DataFrame) -> dict[str, list[dict]] | None:
    """가로형(열이 날짜인 형태)을 날짜별 레코드로."""
    header = list(raw.iloc[0].values)
    date_cols = [(i, d) for i, c in enumerate(header)
                 if i >= 2 and (d := parse_date(c))]
    if not date_cols:
        return None

    body = raw.iloc[1:]
    out: dict[str, list[dict]] = {}
    for col, date in date_cols:
        rows = []
        for _, r in body.iterrows():
            name = str(r.iloc[1]).strip() if len(r) > 1 else ""
            if not name or name.lower() in ("nan", "none") or "합계" in name:
                continue
            w = pd.to_numeric(r.iloc[col], errors="coerce")
            if pd.isna(w) or float(w) == 0:
                continue
            code = str(r.iloc[0]).strip()
            if code.lower() in ("nan", "none", ""):
                code = "CASH" if "현금" in name else ""
            rows.append({"티커": code, "구성종목명": name, "계약수": 0,
                         "평가금액": 0, "비중": round(float(w), 4)})
        if rows:
            out[date] = rows
    return out or None


def import_file(path) -> tuple[int, int]:
    ticker = ticker_of(path)
    if not ticker:
        print(f"  [건너뜀] {path.name}: 파일명 앞에 6자리 티커가 없습니다")
        return 0, 0

    book = pd.read_excel(path, sheet_name=None, header=None)
    by_date = None
    for sheet, raw in book.items():
        by_date = read_long(raw) or read_wide(raw)
        if by_date:
            print(f"  {path.name} · 시트 '{sheet}' · {ticker} · 날짜 {len(by_date)}개")
            break
    if not by_date:
        print(f"  [실패] {path.name}: 알아볼 수 있는 표가 없습니다")
        return 0, 0

    out_dir = DATA_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for date, rows in sorted(by_date.items()):
        target = out_dir / f"{date}.csv"
        if target.exists():
            skipped += 1
            continue
        pd.DataFrame(rows).to_csv(target, index=False, encoding="utf-8-sig")
        written += 1
    print(f"     신규 {written}일 / 기존 유지 {skipped}일")
    return written, skipped


def main() -> int:
    if not LEGACY_DIR.exists():
        print(f"이관할 폴더가 없습니다: {LEGACY_DIR} (건너뜁니다)")
        return 0

    files = sorted(LEGACY_DIR.glob("*.xlsx"))
    if not files:
        print("이관할 엑셀이 없습니다 (건너뜁니다)")
        return 0

    print(f"[이관 시작] 파일 {len(files)}개")
    total = 0
    for f in files:
        total += import_file(f)[0]
    print(f"[이관 완료] 신규 저장 {total}일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
