"""Step 4: 품목별 소스(국제가·수입단가·PPI·CPI·도매가) 통합 + 결측 보간."""

import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MERGED_DIR = PROCESSED_DIR / "merged"
MERGED_DIR.mkdir(parents=True, exist_ok=True)


def load_sources():
    """전처리 소스 CSV 로드."""
    sources = {}

    sources["worldbank"] = pd.read_csv(
        PROCESSED_DIR / "worldbank_prices_krw.csv", parse_dates=["date"]
    )
    sources["customs"] = pd.read_csv(
        RAW_DIR / "customs" / "customs_import_prices.csv", parse_dates=["date"]
    )
    sources["ecos"] = pd.read_csv(
        RAW_DIR / "ecos" / "ecos_ppi_cpi.csv", parse_dates=["date"]
    )
    sources["exchange_rate"] = pd.read_csv(
        RAW_DIR / "exchange_rate" / "exchange_rate_monthly.csv", parse_dates=["date"]
    )

    kamis_path = RAW_DIR / "kamis" / "kamis_wholesale_monthly.csv"
    sources["kamis"] = pd.read_csv(kamis_path, parse_dates=["date"]) if kamis_path.exists() else pd.DataFrame()

    fao_path = RAW_DIR / "fao" / "fao_ffpi_monthly.csv"
    sources["fao"] = pd.read_csv(fao_path, parse_dates=["date"]) if fao_path.exists() else pd.DataFrame()

    sources["common_periods"] = pd.read_csv(
        PROCESSED_DIR / "common_periods.csv",
        parse_dates=["common_start", "common_end"]
    )

    for key in ["worldbank", "customs", "ecos", "kamis", "exchange_rate", "fao"]:
        df = sources[key]
        if not df.empty and "date" in df.columns:
            df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()

    return sources


def interpolate_series(series):
    """선형 보간 후 양 끝 결측은 ffill/bfill로 채움."""
    result = series.interpolate(method="linear")
    result = result.ffill().bfill()
    return result


def merge_single_commodity(cid, commodity_config, sources):
    """단일 품목의 소스를 공통 기간 기준으로 merge."""
    has_wholesale = commodity_config.get("has_wholesale", False)

    cp = sources["common_periods"]
    cp_row = cp[cp["commodity_id"] == cid]
    if cp_row.empty or cp_row.iloc[0]["common_months"] == 0:
        return pd.DataFrame()

    start = cp_row.iloc[0]["common_start"]
    end = cp_row.iloc[0]["common_end"]

    date_range = pd.date_range(start=start, end=end, freq="MS")
    result = pd.DataFrame({"date": date_range})

    wb = sources["worldbank"]
    wb_sub = wb[wb["commodity_id"] == cid][["date", "price_usd_mt", "price_krw_mt"]].copy()
    result = result.merge(wb_sub, on="date", how="left")
    result = result.rename(columns={
        "price_usd_mt": "intl_price_usd",
        "price_krw_mt": "intl_price_krw",
    })

    exrate = sources["exchange_rate"][["date", "exchange_rate_avg"]].copy()
    result = result.merge(exrate, on="date", how="left")
    result = result.rename(columns={"exchange_rate_avg": "exchange_rate"})

    cu = sources["customs"]
    cu_sub = cu[cu["commodity_id"] == cid][["date", "import_unit_price"]].copy()
    result = result.merge(cu_sub, on="date", how="left")
    result = result.rename(columns={"import_unit_price": "import_price_usd"})

    ecos = sources["ecos"]
    ppi = ecos[(ecos["commodity_id"] == cid) & (ecos["data_type"] == "ppi")]
    ppi_sub = ppi[["date", "value"]].copy()
    result = result.merge(ppi_sub, on="date", how="left")
    result = result.rename(columns={"value": "ppi"})

    cpi = ecos[(ecos["commodity_id"] == cid) & (ecos["data_type"] == "cpi")]
    cpi_sub = cpi[["date", "value"]].copy()
    result = result.merge(cpi_sub, on="date", how="left")
    result = result.rename(columns={"value": "cpi"})

    if has_wholesale and not sources["kamis"].empty:
        kamis = sources["kamis"]
        kamis_sub = kamis[kamis["commodity_id"] == cid][["date", "price"]].copy()
        result = result.merge(kamis_sub, on="date", how="left")
        result = result.rename(columns={"price": "wholesale_price"})
    else:
        result["wholesale_price"] = np.nan

    value_cols = ["intl_price_usd", "intl_price_krw", "exchange_rate",
                  "import_price_usd", "ppi", "cpi", "wholesale_price"]
    for col in value_cols:
        if col in result.columns and result[col].notna().any():
            result[col] = interpolate_series(result[col])

    result.insert(0, "commodity_id", cid)

    if not has_wholesale and "wholesale_price" in result.columns:
        result = result.drop(columns=["wholesale_price"])

    return result


def merge_all_datasets():
    print("=" * 60)
    print("  Step 4: 품목별 통합 데이터셋 생성")
    print("=" * 60)

    sources = load_sources()

    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    all_merged = []

    print(f"\n  {'품목':<12} {'기간':<25} {'월수':>5} {'컬럼수':>5} {'결측합계':>7}")
    print(f"  {'─'*65}")

    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        name_kr = commodity["name_kr"]

        merged = merge_single_commodity(cid, commodity, sources)

        if merged.empty:
            print(f"  {name_kr:<12} — 건너뜀 (공통 기간 없음)")
            continue

        item_path = MERGED_DIR / f"{cid}.csv"
        merged.to_csv(item_path, index=False, encoding="utf-8-sig")

        value_cols = [c for c in merged.columns if c not in ["date", "commodity_id"]]
        remaining_missing = merged[value_cols].isna().sum().sum()

        period_str = f"{merged['date'].min().strftime('%Y-%m')}~{merged['date'].max().strftime('%Y-%m')}"
        print(f"  {name_kr:<12} {period_str:<25} {len(merged):>5} {len(merged.columns):>5} {remaining_missing:>7}")

        all_merged.append(merged)

    if all_merged:
        full_df = pd.concat(all_merged, ignore_index=True)
        full_path = MERGED_DIR / "all_commodities.csv"
        full_df.to_csv(full_path, index=False, encoding="utf-8-sig")
        print(f"\n  💾 전체 통합: {full_path} ({len(full_df)}행)")

    print(f"\n  💾 개별 품목 파일:")
    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        item_path = MERGED_DIR / f"{cid}.csv"
        if item_path.exists():
            print(f"    {item_path.name}")

    return full_df if all_merged else pd.DataFrame()


if __name__ == "__main__":
    merge_all_datasets()
