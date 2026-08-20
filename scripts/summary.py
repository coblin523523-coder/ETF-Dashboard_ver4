"""ETF 3종을 가로질러 보는 Summary 자료를 만든다.

  1. 주요 투자 섹터  — ETF별 섹터 비중과 그 섹터에 속한 종목
  2. 섹터 변화      — 비중이 눈에 띄게 움직인 섹터를 날짜별로 누적 기록

섹터 비중은 그 섹터에 속한 종목들의 비중을 그대로 더한 값이다.
"""

from __future__ import annotations

import collections

from sectors import SECTOR_ORDER, classify, sort_key

# 이만큼(%p) 이상 움직인 섹터만 '변화'로 본다.
# 너무 낮추면 매일 잡음이 쌓이고, 너무 높이면 흐름을 놓친다.
CHANGE_THRESHOLD = 1.5

# 한 날짜에 기록할 최대 이벤트 수 (같은 날 모든 섹터가 흔들려도 상위 것만)
MAX_EVENTS_PER_DAY = 3

# 변화를 이끈 종목을 몇 개까지 보여줄지
MAX_DRIVERS = 3


def sector_weights(rows: list[dict]) -> dict[str, float]:
    agg: dict[str, float] = collections.defaultdict(float)
    for r in rows:
        agg[classify(r["name"])] += r["weight"]
    return dict(agg)


def sector_members(rows: list[dict]) -> dict[str, list[dict]]:
    members: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        members[classify(r["name"])].append(
            {"name": r["name"], "weight": round(r["weight"], 2)}
        )
    for sec in members:
        members[sec].sort(key=lambda x: -x["weight"])
    return dict(members)


def _by_date(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for r in records:
        out[r["date"]].append(r)
    return out


def latest_breakdown(records: list[dict]) -> dict | None:
    """최신 날짜의 섹터별 비중과 소속 종목."""
    if not records:
        return None
    by_date = _by_date(records)
    date = max(by_date)
    rows = by_date[date]

    weights = sector_weights(rows)
    members = sector_members(rows)
    sectors = [
        {
            "sector": s,
            "weight": round(w, 2),
            "count": len(members.get(s, [])),
            "members": members.get(s, [])[:8],
        }
        for s, w in weights.items() if w > 0
    ]
    sectors.sort(key=lambda x: -x["weight"])
    return {"date": date, "sectors": sectors}


def change_events(records: list[dict], etf: dict) -> list[dict]:
    """연속한 두 수집일 사이에 섹터 비중이 크게 움직인 사건을 모은다."""
    by_date = _by_date(records)
    dates = sorted(by_date)
    events: list[dict] = []

    for i in range(1, len(dates)):
        prev_d, cur_d = dates[i - 1], dates[i]
        prev_w = sector_weights(by_date[prev_d])
        cur_w = sector_weights(by_date[cur_d])

        # 그 섹터 안에서 어떤 종목이 움직였는지 찾기 위한 종목별 비중
        prev_stock = {r["name"]: r["weight"] for r in by_date[prev_d]}
        cur_stock = {r["name"]: r["weight"] for r in by_date[cur_d]}

        day: list[dict] = []
        for sec in set(prev_w) | set(cur_w):
            a, b = prev_w.get(sec, 0.0), cur_w.get(sec, 0.0)
            delta = b - a
            if abs(delta) < CHANGE_THRESHOLD:
                continue

            drivers = []
            names = {n for n in set(prev_stock) | set(cur_stock)
                     if classify(n) == sec}
            for n in names:
                d = cur_stock.get(n, 0.0) - prev_stock.get(n, 0.0)
                if abs(d) < 0.3:
                    continue
                drivers.append({
                    "name": n,
                    "delta": round(d, 2),
                    "status": ("편입" if n not in prev_stock else
                               "편출" if n not in cur_stock else ""),
                })
            drivers.sort(key=lambda x: -abs(x["delta"]))

            day.append({
                "date": cur_d, "prev_date": prev_d,
                "ticker": etf["ticker"], "etf": etf["short"],
                "sector": sec,
                "prev": round(a, 2), "cur": round(b, 2), "delta": round(delta, 2),
                "drivers": drivers[:MAX_DRIVERS],
            })

        day.sort(key=lambda x: -abs(x["delta"]))
        events.extend(day[:MAX_EVENTS_PER_DAY])

    events.sort(key=lambda x: (x["date"], abs(x["delta"])), reverse=True)
    return events


def build(per_etf: dict[str, list[dict]], etfs: list[dict]) -> dict:
    """per_etf: {티커: records}. render 가 그대로 쓸 수 있는 형태로 돌려준다."""
    breakdown = {}
    events: list[dict] = []
    for etf in etfs:
        recs = per_etf.get(etf["ticker"]) or []
        breakdown[etf["ticker"]] = latest_breakdown(recs)
        events.extend(change_events(recs, etf))

    events.sort(key=lambda x: (x["date"], abs(x["delta"])), reverse=True)

    # 3열 비교표에 쓸 섹터 순서: 세 ETF 합산 비중이 큰 순
    total: dict[str, float] = collections.defaultdict(float)
    for b in breakdown.values():
        if b:
            for s in b["sectors"]:
                total[s["sector"]] += s["weight"]
    order = sorted(total, key=lambda s: (-total[s], sort_key(s)))

    return {"breakdown": breakdown, "events": events, "sector_order": order}
