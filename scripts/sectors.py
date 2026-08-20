"""구성종목을 AI 밸류체인 섹터로 분류한다.

GICS 같은 표준 분류를 쓰면 이 세 ETF는 대부분 '정보기술' 한 덩어리가 되어
아무것도 구분되지 않는다. 그래서 AI 투자에서 실제로 의미가 갈리는 축
(칩 / 메모리 / 장비 / 광통신 / 데이터센터 / 소프트웨어 / 로봇 / 전력)으로 나눈다.

같은 종목이 날마다 다른 표기로 오기 때문에('NVIDIA Corp' vs 'NVIDIA CORP')
이름을 정규화한 뒤 키워드 규칙으로 분류한다. 규칙은 위에서부터 먼저 맞는 것이 이긴다.
"""

from __future__ import annotations

import re

# 화면에 이 순서로 노출된다
SECTOR_ORDER = [
    "AI 반도체",
    "메모리·스토리지",
    "반도체 장비·소재",
    "네트워크·광통신",
    "클라우드·데이터센터",
    "AI 소프트웨어·보안",
    "인터넷·플랫폼",
    "로보틱스·자율주행",
    "전력·에너지 인프라",
    "우주·방산",
    "양자컴퓨팅",
    "핀테크·디지털자산",
    "기타",
    "현금성·파생",
]

# 법인 형태 등 분류에 무의미한 꼬리표
_NOISE = re.compile(
    r"\b(INC|CORP|CORPORATION|LTD|LIMITED|PLC|CO|COMPANY|GROUP|HOLDINGS?|"
    r"SA|AG|NV|SE|ADR|SP|ORD|CL|CLASS|A|B|C|W\s*I|DE|THE|TECHNOLOGIES|"
    r"TECHNOLOGY|TECH)\b", re.I)


def normalize(name: str) -> str:
    s = str(name).upper().strip()
    s = re.sub(r"[/\-–,\.\(\)]", " ", s)
    s = _NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# (섹터, 이 문자열이 정규화된 이름 안에 있으면 해당 섹터)
# 위에서부터 먼저 맞는 규칙이 이긴다. 순서가 곧 우선순위다.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("현금성·파생", (
        "현금", "원화예금", "설정현금", "CASH", "NASDAQ 100 E MINI", "E MINI INDEX",
    )),
    ("기타", (
        "KODEX", "TIME 차이나", "TIME 글로벌", "KOACT",
    )),
    ("메모리·스토리지", (
        "SK HYNIX", "SK하이닉스", "MICRON", "KIOXIA", "SANDISK", "WESTERN DIGITAL",
        "SEAGATE", "NETAPP", "파두", "티엘비", "SILICON MOTION",
    )),
    ("반도체 장비·소재", (
        "ASML", "APPLIED MATERIALS", "LAM RESEARCH", "KLA", "TERADYNE", "ADVANTEST",
        "ONTO INNOVATION", "FORMFACTOR", "AEHR", "NAURA", "KEYSIGHT", "IBIDEN",
        "MURATA", "삼성전기", "LG이노텍", "SYNOPSYS", "SUZHOU DONGSHAN",
        "피에스케이", "미코", "테스", "가온칩스", "티에스이", "고영", "AXT",
    )),
    ("네트워크·광통신", (
        "ARISTA", "CIENA", "COHERENT", "LUMENTUM", "APPLIED OPTOELECTRONICS",
        "FABRINET", "CORNING", "IPG PHOTONICS", "VIAVI", "ZHONGJI", "EOPTOLINK",
        "FUJIKURA", "FURUKAWA", "대한광통신", "이수페타시스", "MACOM",
    )),
    ("AI 반도체", (
        "NVIDIA", "ADVANCED MICRO DEVICES", "BROADCOM", "MARVELL", "QUALCOMM",
        "ARM ", "ARM HOLDINGS", "INTEL", "TAIWAN SEMICONDUCTOR", "ASTERA",
        "CREDO", "RAMBUS", "NAVITAS", "GLOBALFOUNDRIES", "HUA HONG", "HYGON",
        "TOWER SEMICONDUCTOR", "TEXAS INSTRUMENTS", "ANALOG DEVICES",
        "INFINEON", "GIGADEVICE", "SEMICONDUCTOR", "삼성전자",
    )),
    ("클라우드·데이터센터", (
        "AMAZON", "MICROSOFT", "ORACLE", "COREWEAVE", "NEBIUS", "IREN",
        "DIGITALOCEAN", "DELL", "VERTIV", "CELESTICA", "COMFORT SYSTEMS",
    )),
    ("AI 소프트웨어·보안", (
        "PALANTIR", "SNOWFLAKE", "MONGODB", "DATADOG", "DYNATRACE", "SERVICENOW",
        "SALESFORCE", "ATLASSIAN", "CLOUDFLARE", "AKAMAI", "FASTLY", "OKTA",
        "CROWDSTRIKE", "PALO ALTO", "FORTINET", "SAP", "INTERNATIONAL BUSINESS",
        "SAMSARA", "TEMPUS", "ACCENTURE", "MINIMAX", "Z AI", "KNOWLEDGE ATLAS",
        "삼성에스디에스", "현대오토에버",
    )),
    ("인터넷·플랫폼", (
        "ALPHABET", "META PLATFORMS", "NETFLIX", "REDDIT", "BAIDU", "TENCENT",
        "ALIBABA", "PDD", "MERCADOLIBRE", "EBAY", "ZILLOW", "TAKE TWO",
        "ROBLOX", "APPLOVIN", "TRADE DESK", "NAVER", "카카오", "YANDEX",
        "APPLE", "SONY", "XIAOMI", "ECHOSTAR",
    )),
    ("로보틱스·자율주행", (
        "TESLA", "UBTECH", "SERVE ROBOTICS", "INTUITIVE SURGICAL", "AEROVIRONMENT",
        "ONDAS", "로보티즈", "레인보우로보틱스", "에스피지", "하이젠알앤엠", "스피어",
        "현대모비스", "현대차", "ROPER",
    )),
    ("우주·방산", (
        "ROCKET LAB", "FIREFLY", "PLANET LABS", "AST SPACEMOBILE",
        "INTUITIVE MACHINES", "SPACE EXPLORATION", "ELBIT", "BWX",
    )),
    ("양자컴퓨팅", (
        "IONQ", "D WAVE", "RIGETTI", "XANADU",
    )),
    ("핀테크·디지털자산", (
        "COINBASE", "CIRCLE INTERNET", "ROBINHOOD", "SOFI", "INTERACTIVE BROKERS",
        "STRATEGY", "LEMONADE",
    )),
    ("전력·에너지 인프라", (
        "GE VERNOVA", "EATON", "VISTRA", "CONSTELLATION", "TALEN", "NUSCALE",
        "OKLO", "BLOOM ENERGY", "FIRST SOLAR", "JINKOSOLAR", "SUNGROW",
        "FLUENCE", "EOS ENERGY", "GENERAC", "SOLARIS", "MASTEC", "SIEMENS ENERGY",
        "CAMECO", "CENTRUS", "URANIUM", "ENERGY FUELS", "VICOR", "SHOALS",
        "GANFENG", "MP MATERIALS", "WEICHAI", "두산에너빌리티", "HD현대일렉트릭",
        "LS ELECTRIC", "효성중공업", "SNT에너지", "비에이치아이", "삼성SDI",
        "비나텍", "RF머트리얼즈",
    )),
    ("기타", (
        "NATERA",
    )),
]

_CACHE: dict[str, str] = {}


def classify(name: str) -> str:
    """종목명 -> 섹터. 어느 규칙에도 안 걸리면 '미분류'."""
    key = str(name).strip()
    if key in _CACHE:
        return _CACHE[key]

    norm = normalize(key)
    raw = str(key).upper()
    sector = "미분류"
    for sec, keys in RULES:
        if any(k in norm or k in raw for k in keys):
            sector = sec
            break
    _CACHE[key] = sector
    return sector


def sort_key(sector: str) -> int:
    return SECTOR_ORDER.index(sector) if sector in SECTOR_ORDER else len(SECTOR_ORDER)
