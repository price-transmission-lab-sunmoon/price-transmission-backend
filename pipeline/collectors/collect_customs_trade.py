"""관세청 수출입무역통계 Open API를 통한 월별 수입단가($/톤) 수집.

EXIM_API_KEY(공공데이터포털) 사용.
numOfRows=1000은 타임아웃 발생으로 100 사용.
totalCount 필드 없으므로 len(items) < numOfRows 로 마지막 페이지 판단.
"""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("EXIM_API_KEY", "")
if not API_KEY:
    raise SystemExit("EXIM_API_KEY not set in .env")

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "customs"
RAW_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
PAGE_SIZE = 100   # 1000은 타임아웃 발생
REQUEST_DELAY = 0.2  # 초
MAX_RETRIES = 3

# HS 4자리 코드를 commodity_id로 매핑 (parse_customs.py 와 동일)
HS4_TO_COMMODITY: dict[str, str] = {
    "1001": "wheat",
    "1005": "maize",
    "1201": "soybean",
    "1511": "palmoil",
    "1701": "sugar",
    "0901": "coffee",
    "0201": "beef",
    "0202": "beef",
    "1202": "groundnuts",
    "0803": "banana",
    "0805": "orange",
}


def _fetch_page(hs4: str, yymm: str, page: int) -> ET.Element | None:
    """단일 월의 특정 페이지를 호출한다."""
    params = {
        "serviceKey": API_KEY,
        "strtYymm": yymm,
        "endYymm": yymm,
        "hsSgn": hs4,
        "numOfRows": PAGE_SIZE,
        "pageNo": page,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
            else:
                print(f"    [오류] HS {hs4} {yymm} p{page}: {e}")
                return None
    return None


def _collect_one_month(hs4: str, yymm: str) -> tuple[float, float]:
    """한 달치 HS4 수입총액(USD), 중량(kg) 합계 반환."""
    total_dlr = 0.0
    total_wgt = 0.0
    page = 1
    while True:
        root = _fetch_page(hs4, yymm, page)
        if root is None:
            break
        items = root.findall(".//item")
        if not items:
            break
        for item in items:
            year_txt = (item.findtext("year") or "").strip()
            # '총계' 행 제외, 날짜 형식(2022.01)만 처리
            if not re.match(r"\d{4}\.\d{2}", year_txt):
                continue
            hs_cd = (item.findtext("hsCd") or "").strip()
            if hs_cd == "-" or not hs_cd.startswith(hs4):
                continue
            try:
                dlr = float(item.findtext("impDlr") or 0)
                wgt = float(item.findtext("impWgt") or 0)
            except ValueError:
                continue
            total_dlr += dlr
            total_wgt += wgt
        # totalCount 없으므로 페이지 항목 수로 종료 판단
        if len(items) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return total_dlr, total_wgt


def collect_customs_trade(start_year: int = 2020, end_year: int = 2024) -> pd.DataFrame:
    print("=" * 60)
    print("  관세청 Open API 수입단가 수집")
    print(f"  기간: {start_year} ~ {end_year}")
    print("=" * 60)

    records: list[dict] = []
    hs_codes = sorted(set(HS4_TO_COMMODITY.keys()))
    total_hs = len(hs_codes)
    total_months = (end_year - start_year + 1) * 12

    for hs_idx, hs4 in enumerate(hs_codes, 1):
        cid = HS4_TO_COMMODITY[hs4]
        print(f"\n  [{hs_idx}/{total_hs}] {cid} (HS {hs4})")
        year_summary: dict[int, int] = {}

        for yr in range(start_year, end_year + 1):
            months_ok = 0
            for mo in range(1, 13):
                yymm = f"{yr}{mo:02d}"
                dlr, wgt = _collect_one_month(hs4, yymm)
                if wgt > 0:
                    records.append({
                        "date": pd.Timestamp(yr, mo, 1),
                        "commodity_id": cid,
                        "hs_code": hs4,
                        "import_price_usd": dlr / wgt * 1000.0,
                        "import_weight_kg": wgt,
                        "import_value_usd": dlr,
                    })
                    months_ok += 1
                time.sleep(REQUEST_DELAY)
            year_summary[yr] = months_ok
            print(f"    {yr}: {months_ok}/12개월 수집", flush=True)

    if not records:
        print("\n  수집된 데이터 없음")
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # beef: 0201+0202 동월 합산 후 단가 재계산
    beef = (
        df[df["commodity_id"] == "beef"]
        .groupby("date", as_index=False)[["import_value_usd", "import_weight_kg"]]
        .sum()
    )
    if not beef.empty:
        beef["import_price_usd"] = beef["import_value_usd"] / beef["import_weight_kg"] * 1000.0
        beef["commodity_id"] = "beef"
        beef["hs_code"] = "0201"
        df = pd.concat([df[df["commodity_id"] != "beef"], beef], ignore_index=True)

    df = df.sort_values(["commodity_id", "date"]).reset_index(drop=True)

    out = RAW_DIR / "customs_import_prices.csv"
    export = df[["date", "commodity_id", "import_price_usd"]].copy().rename(columns={"import_price_usd": "import_unit_price"})
    export.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  저장: {out} ({len(export)}건)")
    for cid in sorted(export["commodity_id"].unique()):
        sub = export[export["commodity_id"] == cid]
        print(
            f"    {cid:<12} {len(sub):>4}개월  "
            f"{sub['date'].min().strftime('%Y-%m')}~{sub['date'].max().strftime('%Y-%m')}"
        )
    return export


if __name__ == "__main__":
    collect_customs_trade()
