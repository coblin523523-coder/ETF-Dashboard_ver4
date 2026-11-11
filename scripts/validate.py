"""ETF 수집 데이터 품질 및 무결성 검증 스크립트.

8가지 핵심 검증 항목:
  1. 기본 컬럼/형태: 헤더 및 컬럼 구조, 행 개수, 필수 값 누락 여부
  2. 비중 합: 100% ± 1% (99.0% ~ 101.0%, KNOWN_ANOMALY 예외 처리)
  3. 종목 수 하한: 절대 15개 이상, 직전 영업일 대비 70% 이상
  4. 해외종목 존재 여부: 글로벌 AI ETF 특성상 해외종목 필수 (국내종목만 있으면 실패)
  5. 단일종목 비중 상한: 단일 종목 비중 40% 이하 (재정규화/비정상 비중 탐지)
  6. 티커 포맷 급변 탐지: 전일 대비 티커 체계 급변 탐지 (ISIN ↔ 심볼 등)
  7. 중복 티커 탐지: 동일 파일 내 중복 티커 존재 여부
  8. 전일 대비 회전율: 일일 턴오버 (40% 초과 경고, 60% 초과 실패)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

REQUIRED_COLUMNS = ["티커", "구성종목명", "계약수", "평가금액", "비중"]

# 운용사 사유로 비중합이나 구성이 예외적인 것으로 확인된 기수집 날짜 예외 목록
KNOWN_ANOMALIES: set[tuple[str, str]] = {
    # (ticker, date): 사유
}

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
KRX_6DIGIT_RE = re.compile(r"^\d{6}$")


class ValidationError(Exception):
    pass


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValidationError(f"파일이 존재하지 않습니다: {path}")
    if path.stat().st_size == 0:
        raise ValidationError(f"파일이 비어 있습니다 (0 bytes): {path}")

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        for col in REQUIRED_COLUMNS:
            if col not in header:
                raise ValidationError(
                    f"필수 컬럼 '{col}'이 누락되었습니다. 현재 헤더: {header}"
                )
        rows = list(reader)

    if not rows:
        raise ValidationError("데이터 행이 없습니다 (헤더만 존재).")
    return rows


def parse_weight(val: str, row_idx: int) -> float:
    try:
        return float(val.strip().replace(",", ""))
    except (ValueError, TypeError):
        raise ValidationError(f"행 {row_idx}: 잘못된 비중 값 '{val}'")


def get_prev_csv(ticker: str, current_date: str) -> Path | None:
    ticker_dir = DATA_DIR / ticker
    if not ticker_dir.exists():
        return None
    files = sorted([f for f in ticker_dir.glob("*.csv") if f.stem < current_date])
    return files[-1] if files else None


def detect_ticker_format(ticker: str) -> str:
    t = ticker.strip()
    if not t or t.upper() in ("CASH", "KRW", "현금"):
        return "CASH"
    if ISIN_RE.match(t):
        return "ISIN"
    if KRX_6DIGIT_RE.match(t):
        return "KR_CODE"
    if re.match(r"^[A-Z0-9\.\-]+$", t):
        return "SYMBOL"
    return "OTHER"


def is_foreign_asset(ticker: str, name: str) -> bool:
    t = ticker.strip().upper()
    fmt = detect_ticker_format(t)
    if fmt == "ISIN" and not t.startswith("KR"):
        return True
    if fmt == "SYMBOL" and fmt != "CASH":
        return True
    # 종목명에 영문이 주를 이루거나 외국 주식 표시가 있는 경우
    if re.search(r"[a-zA-Z]{3,}", name):
        # 국내 기업명 영문 표기 예외
        if not re.search(r"삼성|SK|LG|현대|NAVER|카카오", name, re.IGNORECASE):
            return True
    return False


def validate_file(ticker: str, date: str) -> list[str]:
    """한 개 파일에 대해 8가지 검증 수행. 경고 메시지 목록을 반환하며, 치명적 오류 시 ValidationError 발생."""
    warnings: list[str] = []
    path = DATA_DIR / ticker / f"{date}.csv"
    rows = load_csv(path)

    # 1. 기본 형태 검증 및 데이터 파싱
    total_weight = 0.0
    weights: list[float] = []
    names: list[str] = []
    tickers: list[str] = []

    for i, r in enumerate(rows, start=2):
        w = parse_weight(r.get("비중", "0"), i)
        weights.append(w)
        total_weight += w
        name = r.get("구성종목명", "").strip()
        t = r.get("티커", "").strip()
        if not name:
            raise ValidationError(f"행 {i}: 구성종목명이 비어 있습니다.")
        names.append(name)
        tickers.append(t)

    # 2. 비중 합 검증 (100% ± 1%)
    if (ticker, date) not in KNOWN_ANOMALIES:
        if not (99.0 <= total_weight <= 101.0):
            raise ValidationError(
                f"비중 합이 비정상입니다: {total_weight:.2f}% (허용범위: 99.0% ~ 101.0%)"
            )

    # 직전 영업일 파일 로드
    prev_path = get_prev_csv(ticker, date)
    prev_rows = load_csv(prev_path) if prev_path else None

    # 3. 종목 수 하한 (절대 15개 이상, 전일 대비 70% 이상)
    count = len(rows)
    if count < 15:
        raise ValidationError(f"종목 수가 너무 적습니다: {count}개 (최소 15개 이상 필요)")
    if prev_rows:
        prev_count = len(prev_rows)
        threshold = int(prev_count * 0.70)
        if count < threshold:
            raise ValidationError(
                f"전일 대비 종목 수가 급감했습니다: 전일 {prev_count}개 → 금일 {count}개 (하한 {threshold}개)"
            )

    # 4. 해외종목 존재 여부 (국내종목만 있으면 실패 - KIS류 실패 탐지)
    foreign_count = sum(1 for t, n in zip(tickers, names) if is_foreign_asset(t, n))
    if foreign_count == 0:
        raise ValidationError(
            "해외 종목이 1개도 없습니다. 국내 자산만 수집되었거나 KIS 스크래핑 실패 의심."
        )

    # 5. 단일종목 비중 40% 상한 (재정규화 실패 탐지)
    for name, w in zip(names, weights):
        if "현금" in name or "CASH" in name:
            continue
        if w > 40.0:
            raise ValidationError(
                f"단일 종목 비중이 40%를 초과했습니다: '{name}' {w:.2f}% (재정규화 오류 의심)"
            )

    # 6. 전일 대비 티커 포맷 급변 탐지
    if prev_rows:
        prev_formats = [
            detect_ticker_format(r.get("티커", ""))
            for r in prev_rows
            if detect_ticker_format(r.get("티커", "")) != "CASH"
        ]
        curr_formats = [
            detect_ticker_format(t) for t in tickers if detect_ticker_format(t) != "CASH"
        ]

        if prev_formats and curr_formats:
            prev_isin_ratio = prev_formats.count("ISIN") / len(prev_formats)
            curr_isin_ratio = curr_formats.count("ISIN") / len(curr_formats)
            if abs(prev_isin_ratio - curr_isin_ratio) > 0.50:
                raise ValidationError(
                    f"티커 포맷이 전일 대비 급변했습니다: 전일 ISIN 비율 {prev_isin_ratio:.1%} → 금일 {curr_isin_ratio:.1%}"
                )

    # 7. 중복 티커 탐지
    non_cash_tickers = [
        t for t in tickers if t and t.upper() not in ("CASH", "KRW", "현금", "-")
    ]
    seen_tickers: set[str] = set()
    duplicates: set[str] = set()
    for t in non_cash_tickers:
        if t in seen_tickers:
            duplicates.add(t)
        seen_tickers.add(t)
    if duplicates:
        raise ValidationError(f"중복된 티커가 존재합니다: {sorted(duplicates)}")

    # 8. 전일 대비 회전율 (턴오버: 40% 초과 경고, 60% 초과 실패)
    if prev_rows:
        # 종목별 비중 매핑
        def make_weight_map(r_list: list[dict[str, str]]) -> dict[str, float]:
            wm: dict[str, float] = {}
            for r in r_list:
                key = r.get("티커", "").strip() or r.get("구성종목명", "").strip()
                try:
                    wm[key] = wm.get(key, 0.0) + float(r.get("비중", "0"))
                except ValueError:
                    pass
            return wm

        curr_map = make_weight_map(rows)
        prev_map = make_weight_map(prev_rows)

        all_keys = set(curr_map.keys()) | set(prev_map.keys())
        diff_sum = sum(abs(curr_map.get(k, 0.0) - prev_map.get(k, 0.0)) for k in all_keys)
        turnover = diff_sum / 2.0

        if turnover > 60.0:
            raise ValidationError(
                f"일일 회전율(턴오버)이 비정상적으로 높습니다: {turnover:.2f}% (한도 60% 초과)"
            )
        elif turnover > 40.0:
            warnings.append(
                f"[경고] 일일 회전율이 40%를 초과했습니다: {turnover:.2f}% (대규모 리밸런싱 가능성)"
            )

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF 데이터 검증")
    parser.add_argument("--date", help="검증할 기준일 (YYYYMMDD)")
    parser.add_argument("--ticker", help="검증할 특정 ETF 티커 (기본: 전체)")
    parser.add_argument("--all", action="store_true", help="전체 이력 검증")
    args = parser.parse_args()

    # 대상 티커 결정
    tickers = [args.ticker] if args.ticker else ["456600", "471040", "466950"]

    total_checked = 0
    total_failed = 0
    total_warnings = 0

    print("════════════════════════════════════════════════════════")
    print("           ETF 데이터 무결성 검증 (validate.py)        ")
    print("════════════════════════════════════════════════════════\n")

    for ticker in tickers:
        ticker_dir = DATA_DIR / ticker
        if not ticker_dir.exists():
            print(f"[{ticker}] 디렉터리가 없습니다: {ticker_dir}")
            continue

        files = sorted(ticker_dir.glob("*.csv"))
        if not files:
            print(f"[{ticker}] CSV 파일이 없습니다.")
            continue

        if args.date:
            target_files = [ticker_dir / f"{args.date}.csv"]
        elif args.all:
            target_files = files
        else:
            # 기본: 최신 1건만 검증
            target_files = [files[-1]]

        for f in target_files:
            if not f.exists():
                print(f"❌ [{ticker}] {f.name}: 파일이 존재하지 않습니다.")
                total_failed += 1
                continue

            date = f.stem
            total_checked += 1
            try:
                warns = validate_file(ticker, date)
                if warns:
                    print(f"⚠️  [{ticker}] {date}: 통과 (경고 {len(warns)}건)")
                    for w in warns:
                        print(f"    - {w}")
                    total_warnings += len(warns)
                else:
                    print(f"✅ [{ticker}] {date}: 정상 (검증 8항목 통과)")
            except ValidationError as e:
                print(f"❌ [{ticker}] {date} 검증 실패: {e}")
                total_failed += 1

    print("\n────────────────────────────────────────────────────────")
    print(
        f"검증 완료: 총 {total_checked}건 중 성공 {total_checked - total_failed}건, "
        f"실패 {total_failed}건, 경고 {total_warnings}건"
    )
    print("────────────────────────────────────────────────────────")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
