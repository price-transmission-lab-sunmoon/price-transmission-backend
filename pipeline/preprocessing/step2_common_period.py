"""Step 2: 품목별 소스 기간 교집합 → 공통 분석 기간 산출."""

import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_all_sources():
    """가용 소스 CSV 로드."""
    sources = {}

    wb_path = PROCESSED_DIR / "worldbank_prices_krw.csv"
    if wb_path.exists():
        sources["worldbank"] = pd.read_csv(wb_path, parse_dates=["date"])

    cu_path = RAW_DIR / "customs" / "customs_import_prices.csv"
    if cu_path.exists():
        sources["customs"] = pd.read_csv(cu_path, parse_dates=["date"])

    ecos_path = RAW_DIR / "ecos" / "ecos_ppi_cpi.csv"
    if ecos_path.exists():
        sources["ecos"] = pd.read_csv(ecos_path, parse_dates=["date"])

    exrate_path = RAW_DIR / "exchange_rate" / "exchange_rate_monthly.csv"
    if exrate_path.exists():
        sources["exchange_rate"] = pd.read_csv(exrate_path, parse_dates=["date"])

    kamis_path = RAW_DIR / "kamis" / "kamis_wholesale_monthly.csv"
    if kamis_path.exists():
        sources["kamis"] = pd.read_csv(kamis_path, parse_dates=["date"])

    fao_path = RAW_DIR / "fao" / "fao_ffpi_monthly.csv"
    if fao_path.exists():
        sources["fao"] = pd.read_csv(fao_path, parse_dates=["date"])

    return sources


def find_common_period():
    print("=" * 60)
    print("  Step 2: 공통 분석 기간 확정")
    print("=" * 60)

    sources = load_all_sources()
    print(f"\n  로드된 소스: {list(sources.keys())}")

    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    commodities = mapping.get("commodities", [])

    results = []

    print(f"\n  {'품목':<12} {'소스별 기간':<60} {'공통 기간':<25} {'월수':>5}")
    print(f"  {'─'*105}")

    for commodity in commodities:
        cid = commodity["commodity_id"]
        name_kr = commodity["name_kr"]
        has_wholesale = commodity.get("has_wholesale", False)

        periods = {}

        if "worldbank" in sources:
            wb = sources["worldbank"][sources["worldbank"]["commodity_id"] == cid]
            if not wb.empty:
                periods["WB"] = (wb["date"].min(), wb["date"].max())

        if "customs" in sources:
            cu = sources["customs"][sources["customs"]["commodity_id"] == cid]
            if not cu.empty:
                periods["관세청"] = (cu["date"].min(), cu["date"].max())

        if "ecos" in sources:
            ppi = sources["ecos"][
                (sources["ecos"]["commodity_id"] == cid) &
                (sources["ecos"]["data_type"] == "ppi")
            ]
            if not ppi.empty:
                periods["PPI"] = (ppi["date"].min(), ppi["date"].max())

        if "ecos" in sources:
            cpi = sources["ecos"][
                (sources["ecos"]["commodity_id"] == cid) &
                (sources["ecos"]["data_type"] == "cpi")
            ]
            if not cpi.empty:
                periods["CPI"] = (cpi["date"].min(), cpi["date"].max())

        if "exchange_rate" in sources:
            ex = sources["exchange_rate"]
            periods["환율"] = (ex["date"].min(), ex["date"].max())

        if has_wholesale and "kamis" in sources:
            kamis = sources["kamis"][sources["kamis"]["commodity_id"] == cid]
            if not kamis.empty:
                periods["KAMIS"] = (kamis["date"].min(), kamis["date"].max())

        if periods:
            common_start = max(start for start, _ in periods.values())
            common_end = min(end for _, end in periods.values())
            months = (common_end.year - common_start.year) * 12 + common_end.month - common_start.month + 1

            if common_start > common_end:
                months = 0
                common_str = "❌ 겹치는 기간 없음"
            else:
                common_str = f"{common_start.strftime('%Y-%m')}~{common_end.strftime('%Y-%m')}"
        else:
            common_start = None
            common_end = None
            months = 0
            common_str = "❌ 데이터 없음"

        print(f"  {name_kr}({cid})")
        for src, (s, e) in periods.items():
            print(f"    {src:<8} {s.strftime('%Y-%m')}~{e.strftime('%Y-%m')}")
        print(f"    → 공통: {common_str} ({months}개월)")
        print()

        results.append({
            "commodity_id": cid,
            "name_kr": name_kr,
            "has_wholesale": has_wholesale,
            "common_start": common_start,
            "common_end": common_end,
            "common_months": months,
            "source_count": len(periods),
        })

    valid_results = [r for r in results if r["common_months"] > 0]
    if valid_results:
        global_start = max(r["common_start"] for r in valid_results)
        global_end = min(r["common_end"] for r in valid_results)
        global_months = (global_end.year - global_start.year) * 12 + global_end.month - global_start.month + 1

        print(f"  {'='*60}")
        print(f"  📅 전 품목 공통 분석 가능 기간:")
        print(f"     {global_start.strftime('%Y-%m')} ~ {global_end.strftime('%Y-%m')} ({global_months}개월)")
        print(f"  {'='*60}")

    result_df = pd.DataFrame(results)
    output_path = PROCESSED_DIR / "common_periods.csv"
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장: {output_path}")

    return result_df


if __name__ == "__main__":
    find_common_period()
