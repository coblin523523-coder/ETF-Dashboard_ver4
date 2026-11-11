#!/usr/bin/env python3
"""
미래에셋 브라우저 콘솔에서 추출한 tiger_40days.json을
ETF-Dashboard_ver4/data/466950/ 디렉터리의 CSV 파일들로 일괄 변환 및 검증하는 스크립트.
(파이썬 표준 라이브러리만 사용)
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "scripts"
DATA_DIR = REPO_DIR / "data" / "466950"

REQUIRED_COLUMNS = ["티커", "구성종목명", "계약수", "평가금액", "비중"]


def _num(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "None", "nan"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def same_holdings(rows_a: list[dict], rows_b: list[dict]) -> bool:
    if len(rows_a) != len(rows_b):
        return False
    ka = sorted((r["구성종목명"], round(_num(r["비중"]), 4)) for r in rows_a)
    kb = sorted((r["구성종목명"], round(_num(r["비중"]), 4)) for r in rows_b)
    return ka == kb


def process_json(json_path: Path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_files = sorted(DATA_DIR.glob("*.csv"))
    last_rows = None
    last_date = "none"

    if existing_files:
        last_date = existing_files[-1].stem
        with open(existing_files[-1], "r", encoding="utf-8-sig") as f:
            last_rows = list(csv.DictReader(f))

    saved_count = 0
    skipped_count = 0

    dates = sorted(data.keys())
    print(f"총 {len(dates)}개 일자 데이터 처리 시작...")

    for date in dates:
        items = data[date]
        if not items:
            print(f"  [{date}] 데이터 없음 (휴장일 추정)")
            skipped_count += 1
            continue

        # wkdate 검사 (휴장일 대응)
        wk = str(items[0].get("wkdate") or "").strip()
        if wk and wk != date:
            print(f"  [{date}] 기준일 불일치 ({wk}) -> 휴장일로 간주 건너뜀")
            skipped_count += 1
            continue

        rows = []
        for d in items:
            code = str(d.get("code") or "").strip()
            name = str(d.get("memItemname") or "").strip()
            qty = _num(d.get("stockQty"))
            prc = _num(d.get("stockPrc"))
            rate = _num(d.get("stockRate"))

            if not name:
                continue
            if rate == 0 and prc == 0:
                continue

            # 현금 행 티커 통일
            if re.search(r"현금|설정현금|Cash", name, re.IGNORECASE):
                if code in ("", "nan", "None"):
                    code = "CASH"

            rows.append({
                "티커": code,
                "구성종목명": name,
                "계약수": qty,
                "평가금액": prc,
                "비중": rate,
            })

        if not rows:
            print(f"  [{date}] 유효 행 없음")
            skipped_count += 1
            continue

        # 비중 단위 검사 (비율 vs 백분율)
        total_rate = sum(r["비중"] for r in rows)
        if 0.5 < total_rate < 1.5:
            for r in rows:
                r["비중"] = r["비중"] * 100.0
            total_rate = sum(r["비중"] for r in rows)

        if last_rows is not None and same_holdings(rows, last_rows):
            print(f"  [{date}] {last_date} 와 내용 완전 동일 -> 휴장일로 간주 건너뜀")
            skipped_count += 1
            continue

        out_path = DATA_DIR / f"{date}.csv"
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "티커": r["티커"],
                    "구성종목명": r["구성종목명"],
                    "계약수": f"{r['계약수']:g}" if isinstance(r['계약수'], float) else r['계약수'],
                    "평가금액": f"{r['평가금액']:g}" if isinstance(r['평가금액'], float) else r['평가금액'],
                    "비중": f"{r['비중']:.4f}".rstrip("0").rstrip(".") if isinstance(r['비중'], float) else r['비중'],
                })

        print(f"  ✅ [{date}] 저장 완료: {len(rows)}개 종목, 비중 합계 {total_rate:.2f}%")
        last_rows = rows
        last_date = date
        saved_count += 1

    print("\n" + "=" * 50)
    print(f"처리 결과: 총 {saved_count}개 일자 저장, {skipped_count}개 일자 건너뜀")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
    else:
        # Default search in workspace or downloads
        candidates = list(Path("/workspace").glob("**/tiger_40days.json")) + \
                     list(Path("/workspace/downloads").glob("**/tiger_40days.json")) + \
                     list(Path("/workspace/attachments").glob("**/tiger_40days*.json"))
        if candidates:
            p = candidates[0]
        else:
            print("사용법: python3 process_tiger_json.py <tiger_40days.json 경로>")
            sys.exit(1)

    print(f"처리 대상 파일: {p}")
    process_json(p)
