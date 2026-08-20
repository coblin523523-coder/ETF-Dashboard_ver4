"""운용사별 구성종목 수집기.

세 운용사가 데이터를 내주는 방식이 전부 다르다.

  미래에셋(TIGER)   JSON API. ISIN·비중이 그대로 오고 fixDate로 과거 조회까지 된다.
  삼성액티브(KoAct)  gijunYMD 파라미터가 붙은 엑셀 다운로드. 오늘치는 JSON API에도 있다.
  타임폴리오        날짜 선택이 없다. 오늘치 엑셀 또는 HTML 표만 받을 수 있다.

어느 쪽이든 마지막에는 config.CSV_COLUMNS 형태의 DataFrame 하나로 통일해서 돌려준다.
"""

from __future__ import annotations

import io
import re

import pandas as pd
import requests

from config import CSV_COLUMNS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 30


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    return s


def _num(x) -> float:
    """'1,234.5', '-', '', None 을 모두 float 으로."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return 0.0 if pd.isna(x) else float(x)
    s = str(x).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "None", "nan"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _frame(rows: list[dict]) -> pd.DataFrame:
    """공통 스키마로 정리하고, 이름이 비었거나 비중·평가금액이 모두 0인 행은 버린다."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = 0
    df = df[CSV_COLUMNS]
    df["구성종목명"] = df["구성종목명"].astype(str).str.strip()
    df["티커"] = df["티커"].astype(str).str.strip()
    df = df[df["구성종목명"] != ""]
    # 현금 행은 코드가 비어 오는 경우가 많다. 표기를 통일해 종목 식별이 흔들리지 않게 한다.
    cash = df["구성종목명"].str.contains("현금|설정현금|Cash", case=False, regex=True)
    df.loc[cash & (df["티커"].isin(["", "nan", "None"])), "티커"] = "CASH"
    df = df[(df["비중"] != 0) | (df["평가금액"] != 0)]
    df = df.reset_index(drop=True)

    # 같은 운용사라도 엑셀은 비율(0.0892), API는 퍼센트(8.92)로 준다.
    # 합계가 1 근처면 비율로 보고 100을 곱해 퍼센트로 통일한다.
    total = float(df["비중"].sum())
    if 0.5 < total < 1.5:
        df["비중"] = df["비중"] * 100.0
    return df


def _read_tabular(content: bytes) -> list[pd.DataFrame]:
    """운용사가 내려준 파일을 표로 읽는다.

    확장자가 .xls 라도 실제로는 HTML 표인 경우가 흔해서 순서대로 시도한다.
    """
    attempts = []
    for engine in ("openpyxl", "xlrd", None):
        try:
            kw = {"engine": engine} if engine else {}
            book = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, **kw)
            attempts.extend(book.values())
            if attempts:
                return attempts
        except Exception:
            continue
    try:
        return pd.read_html(io.BytesIO(content))
    except Exception:
        pass
    for enc in ("utf-8-sig", "cp949"):
        try:
            return [pd.read_csv(io.BytesIO(content), header=None, encoding=enc)]
        except Exception:
            continue
    return []


def _pick_holdings_table(tables: list[pd.DataFrame]) -> tuple[pd.DataFrame, dict] | None:
    """표 목록에서 '종목명 + 비중'이 있는 표와 그 컬럼 위치를 찾는다.

    운용사 엑셀은 위에 제목·기준일 등이 몇 줄 붙어 있어서 헤더 행 위치가 일정하지 않다.
    그래서 고정 좌표 대신 키워드로 헤더 행을 찾아낸다.
    """
    name_kw = ("종목명", "종목 명", "구성종목", "name")
    rate_kw = ("비중", "weight", "ratio")
    qty_kw = ("수량", "주식수", "계약수", "qty")
    amt_kw = ("평가금액", "금액", "평가", "amount")
    code_kw = ("종목코드", "코드", "code", "ticker")

    def find(cells, kws):
        for i, c in enumerate(cells):
            t = str(c).strip().lower()
            if any(k.lower() in t for k in kws):
                return i
        return None

    for tb in tables:
        if tb is None or tb.empty:
            continue
        limit = min(len(tb), 30)
        for r in range(limit):
            cells = list(tb.iloc[r].values)
            ni, ri = find(cells, name_kw), find(cells, rate_kw)
            if ni is None or ri is None:
                continue
            body = tb.iloc[r + 1:].reset_index(drop=True)
            return body, {
                "name": ni, "rate": ri,
                "qty": find(cells, qty_kw),
                "amt": find(cells, amt_kw),
                "code": find(cells, code_kw),
            }
    return None


def _from_tabular(content: bytes, label: str) -> pd.DataFrame:
    tables = _read_tabular(content)
    picked = _pick_holdings_table(tables)
    if not picked:
        print(f"    [!] {label}: 구성종목 표를 찾지 못했습니다 (표 {len(tables)}개)")
        return pd.DataFrame()

    body, cols = picked
    rows = []
    for _, row in body.iterrows():
        vals = list(row.values)

        def at(key):
            i = cols.get(key)
            return vals[i] if i is not None and i < len(vals) else None

        name = str(at("name") or "").strip()
        if not name or name.lower() in ("nan", "none") or "합계" in name:
            continue
        rows.append({
            "티커": str(at("code") or "").strip().replace("nan", ""),
            "구성종목명": name,
            "계약수": _num(at("qty")),
            "평가금액": _num(at("amt")),
            "비중": _num(at("rate")),
        })
    return _frame(rows)


# ──────────────────────────────────────────────────────────────
# 미래에셋 (TIGER)
# ──────────────────────────────────────────────────────────────
MIRAE_URL = ("https://investments.miraeasset.com/tigeretf/ko/product/chart/"
             "prdct-item-list.ajax")


MIRAE_DETAIL = ("https://investments.miraeasset.com/tigeretf/ko/product/search/"
                "detail/index.do")

# 세션 쿠키를 매번 새로 받지 않도록 프로세스 안에서 재사용한다
_MIRAE_SESSION: requests.Session | None = None


def _mirae_session(ksd_fund: str) -> requests.Session:
    """상세 페이지를 한 번 열어 세션 쿠키를 확보한다.

    ajax 엔드포인트는 쿠키 없이 부르면 403 을 돌려준다. 브라우저에서는
    페이지를 먼저 열기 때문에 문제가 없지만, 스크립트에서는 그 과정을
    직접 흉내내야 한다.
    """
    global _MIRAE_SESSION
    if _MIRAE_SESSION is not None:
        return _MIRAE_SESSION

    sess = _session()
    referer = f"{MIRAE_DETAIL}?ksdFund={ksd_fund}"
    sess.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://investments.miraeasset.com",
        "Referer": referer,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    })
    try:
        sess.get(referer, timeout=TIMEOUT,
                 headers={"Accept": "text/html,application/xhtml+xml"})
    except Exception as exc:
        print(f"    [!] TIGER 세션 준비 실패: {type(exc).__name__}: {exc}")

    _MIRAE_SESSION = sess
    return sess


_MIRAE_CFFI = None


def _mirae_cffi(ksd_fund: str):
    """크롬 TLS 지문으로 위장한 세션.

    미래에셋은 파이썬 requests 의 TLS 지문을 보고 403 을 돌려준다.
    curl_cffi 는 크롬과 동일한 지문으로 접속해 그 검사를 통과한다.
    라이브러리가 없으면 None 을 돌려주고 일반 requests 로 넘어간다.
    """
    global _MIRAE_CFFI
    if _MIRAE_CFFI is not None:
        return _MIRAE_CFFI
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("    [!] curl_cffi 가 설치되어 있지 않습니다. "
              "requirements.txt 에 'curl_cffi>=0.7' 이 있는지 확인하세요.")
        print("        (이게 없으면 크롬 지문 위장을 시도조차 못 합니다)")
        return None

    sess = creq.Session(impersonate="chrome")
    sess.headers.update({
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": f"{MIRAE_DETAIL}?ksdFund={ksd_fund}",
        "Origin": "https://investments.miraeasset.com",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        sess.get(f"{MIRAE_DETAIL}?ksdFund={ksd_fund}", timeout=TIMEOUT)
    except Exception:
        pass
    _MIRAE_CFFI = sess
    return sess


_MIRAE_DIAGNOSED = False


def _diagnose_mirae(ksd_fund: str) -> None:
    """403 이 났을 때 원인을 한 번만 진단해 출력한다.

    IP 차단이면 홈페이지조차 403 이고, 지문 차단이면 홈페이지는 열린다.
    둘은 대응이 완전히 달라서 구분이 중요하다.
    """
    global _MIRAE_DIAGNOSED
    if _MIRAE_DIAGNOSED:
        return
    _MIRAE_DIAGNOSED = True

    detail = f"{MIRAE_DETAIL}?ksdFund={ksd_fund}"
    print("\n    ── 미래에셋 접근 진단 ──")

    def probe(label, fn):
        try:
            r = fn()
            body = (getattr(r, "text", "") or "")[:120].replace("\n", " ")
            print(f"      {label:<28} {r.status_code}  ({len(r.content):,} bytes)")
            if r.status_code != 200 and body:
                print(f"          본문: {body}")
            return r
        except Exception as exc:
            print(f"      {label:<28} 예외 {type(exc).__name__}: {str(exc)[:70]}")
            return None

    sess = _session()
    probe("홈페이지 (requests)",
          lambda: sess.get("https://investments.miraeasset.com/", timeout=TIMEOUT))
    r = probe("상세페이지 (requests)", lambda: sess.get(detail, timeout=TIMEOUT))
    if r is not None and r.status_code == 200:
        has = ("Advanced Micro" in r.text) or ("구성종목" in r.text)
        print(f"          상세페이지 HTML 에 구성종목 있음? {'예' if has else '아니오'}")

    cffi = _mirae_cffi(ksd_fund)
    if cffi is None:
        print("      curl_cffi                    미설치 — 위장 시도 불가")
    else:
        probe("상세페이지 (크롬 위장)", lambda: cffi.get(detail, timeout=TIMEOUT))
        probe("ajax (크롬 위장)", lambda: cffi.post(
            MIRAE_URL,
            params={"ksdFund": ksd_fund, "prfPrd": "Week01",
                    "fixDate": "20260814", "listCnt": "300"},
            timeout=TIMEOUT))

    print("      판독: 홈페이지도 403 → IP 차단 / 홈페이지만 200 → 지문 차단")
    print("    ────────────────────────\n")


def fetch_mirae(params: dict, date: str) -> pd.DataFrame:
    """TIGER. 응답의 code 가 ISIN 이라 종목 식별이 가장 깔끔하다."""
    q = {"ksdFund": params["ksd_fund"], "prfPrd": "Week01",
         "fixDate": date, "listCnt": "300"}

    resp = None
    cffi = _mirae_cffi(params["ksd_fund"])
    if cffi is not None:
        try:
            r = cffi.post(MIRAE_URL, params=q, timeout=TIMEOUT)
            if r.status_code == 200:
                resp = r
        except Exception:
            resp = None

    if resp is None:
        s = _mirae_session(params["ksd_fund"])
        r = s.post(MIRAE_URL, params=q, timeout=TIMEOUT)
        if r.status_code != 200:
            r = s.get(MIRAE_URL, params=q, timeout=TIMEOUT)
        if r.status_code == 200:
            resp = r
        else:
            # 마지막 수단: 상세페이지 HTML 을 타임폴리오처럼 긁는다.
            # 성공하면 화면에 보이는 상위 종목만 얻는다(전체 목록은 아님).
            df = _mirae_from_page(params["ksd_fund"], date)
            if not df.empty:
                return df
            _diagnose_mirae(params["ksd_fund"])
            r.raise_for_status()

    data = resp.json().get("rtnData") or []
    rows = [{
        "티커": str(d.get("code") or "").strip(),
        "구성종목명": str(d.get("memItemname") or "").strip(),
        "계약수": _num(d.get("stockQty")),
        "평가금액": _num(d.get("stockPrc")),
        "비중": _num(d.get("stockRate")),
    } for d in data]

    df = _frame(rows)
    # 요청한 날짜와 응답 기준일이 다르면(휴장일 등) 그 날짜 데이터가 없는 것으로 본다
    if data:
        wk = str(data[0].get("wkdate") or "").strip()
        if wk and wk != date:
            print(f"    [!] TIGER {date}: 응답 기준일이 {wk} 라 건너뜁니다")
            return pd.DataFrame()
    return df


# ──────────────────────────────────────────────────────────────
# 삼성액티브 (KoAct)
# ──────────────────────────────────────────────────────────────
SAMSUNG_API = "https://www.samsungactive.co.kr/api/v1/product/etf/{fid}.do"
SAMSUNG_XLS = "https://www.samsungactive.co.kr/excel_pdf.do"


def fetch_samsung(params: dict, date: str) -> pd.DataFrame:
    """KoAct. 엑셀이 날짜 파라미터를 받으므로 과거·오늘 모두 엑셀로 받는다.

    엑셀이 실패하면 오늘치에 한해 JSON API로 되돌아간다.
    (JSON 의 pdf.list 는 20개로 잘리지만 pdf.top10 은 온전하다.)
    """
    fid = params["fund_id"]
    s = _session()
    s.headers["Referer"] = f"https://www.samsungactive.co.kr/etf/view.do?id={fid}"

    try:
        r = s.get(SAMSUNG_XLS, params={"fId": fid, "gijunYMD": date}, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            df = _from_tabular(r.content, f"KoAct {date} 엑셀")
            if not df.empty:
                return df
    except Exception as exc:
        print(f"    [!] KoAct {date} 엑셀 실패: {type(exc).__name__}: {exc}")

    # 예비 경로: JSON API (오늘치만 유효)
    try:
        j = s.get(SAMSUNG_API.format(fid=fid), timeout=TIMEOUT).json()
        pdf = j.get("pdf") or {}
        if str(pdf.get("gijunYMD") or "") != date:
            return pd.DataFrame()
        items = pdf.get("list") or pdf.get("top10") or []
        rows = [{
            "티커": str(d.get("itmNo") or "").strip(),
            "구성종목명": str(d.get("secNm") or "").strip(),
            "계약수": _num(d.get("applyQ")),
            "평가금액": _num(d.get("evalA")),
            "비중": _num(d.get("ratio")),
        } for d in items]
        df = _frame(rows)
        if not df.empty:
            print(f"    (KoAct {date}: JSON 예비 경로, {len(df)}종목)")
        return df
    except Exception as exc:
        print(f"    [!] KoAct {date} JSON 실패: {type(exc).__name__}: {exc}")
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────
# 타임폴리오
# ──────────────────────────────────────────────────────────────
TIMEFOLIO_XLS = "https://timeetf.co.kr/pdf_excel.php"
TIMEFOLIO_PAGE = "https://timeetf.co.kr/m11_view.php"


def fetch_timefolio(params: dict, date: str) -> pd.DataFrame:
    """TIMEFOLIO. 사이트가 오늘치만 제공하므로 date 는 저장 파일명 용도로만 쓴다."""
    s = _session()
    s.headers["Referer"] = (
        f"{TIMEFOLIO_PAGE}?idx={params['idx']}&cate={params['cate']}"
    )

    try:
        r = s.get(TIMEFOLIO_XLS,
                  params={"cate": params["cate"], "idx": params["idx"]},
                  timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            df = _from_tabular(r.content, f"TIMEFOLIO {date} 엑셀")
            if not df.empty:
                return df
    except Exception as exc:
        print(f"    [!] TIMEFOLIO 엑셀 실패: {type(exc).__name__}: {exc}")

    # 예비 경로: 상세 페이지의 HTML 표
    try:
        r = s.get(TIMEFOLIO_PAGE,
                  params={"idx": params["idx"], "cate": params["cate"]},
                  timeout=TIMEOUT)
        r.raise_for_status()
        html = r.content
        df = _from_tabular(html, f"TIMEFOLIO {date} HTML")
        if not df.empty:
            print(f"    (TIMEFOLIO {date}: HTML 예비 경로, {len(df)}종목)")
        return df
    except Exception as exc:
        print(f"    [!] TIMEFOLIO HTML 실패: {type(exc).__name__}: {exc}")
        return pd.DataFrame()


def _mirae_from_page(ksd_fund: str, date: str) -> pd.DataFrame:
    """상세페이지 HTML 에서 구성종목 표를 직접 읽는다 (ajax 가 막혔을 때의 우회로).

    주의할 점이 둘 있다.
      - 이 경로로는 오늘치만 얻을 수 있다. 페이지에 날짜 선택이 반영되지 않는다.
      - 페이지가 처음에 상위 10종목만 그리므로 전체 목록이 아닐 수 있다.
        Top10 대시보드에는 충분하지만, 비중 합계는 100%가 되지 않는다.
    """
    # 이 경로는 항상 '오늘 화면'을 준다. 과거 날짜로 250번 부르면 같은 데이터를
    # 반복해서 받게 되므로, 최근 며칠 요청에 대해서만 시도한다.
    try:
        from datetime import datetime, timedelta
        if datetime.strptime(date, "%Y%m%d") < datetime.now() - timedelta(days=6):
            return pd.DataFrame()
    except ValueError:
        return pd.DataFrame()

    url = f"{MIRAE_DETAIL}?ksdFund={ksd_fund}"
    html = None

    cffi = _mirae_cffi(ksd_fund)
    if cffi is not None:
        try:
            r = cffi.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                html = r.content
        except Exception:
            html = None

    if html is None:
        try:
            r = _session().get(url, timeout=TIMEOUT,
                               headers={"Accept": "text/html,application/xhtml+xml"})
            if r.status_code == 200:
                html = r.content
        except Exception:
            return pd.DataFrame()

    if not html:
        return pd.DataFrame()

    df = _from_tabular(html, f"TIGER {date} 상세페이지")
    if not df.empty:
        print(f"    (TIGER {date}: 상세페이지 HTML 경로, {len(df)}종목 "
              f"— 화면에 보이는 상위 종목만일 수 있습니다)")
    return df


FETCHERS = {
    "mirae": fetch_mirae,
    "samsung": fetch_samsung,
    "timefolio": fetch_timefolio,
}


def fetch(etf: dict, date: str) -> pd.DataFrame:
    fn = FETCHERS.get(etf["source"])
    if fn is None:
        raise ValueError(f"알 수 없는 source: {etf['source']}")
    return fn(etf["params"], date)
