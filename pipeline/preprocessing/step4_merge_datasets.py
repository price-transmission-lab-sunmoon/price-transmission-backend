"""
Phase 0 전처리 — Step 4: 품목별 통합 데이터셋 생성
==============================================
각 품목의 국제가(원화), 수입단가, PPI, CPI, (도매가)를
하나의 시계열로 merge하고 결측치 보간을 적용합니다.
실행: python src/preprocessing/step4_merge_datasets.py
"""

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
    """모든 소스 데이터 로드"""
    sources = {}

    # World Bank (원화 환산)
    sources["worldbank"] = pd.read_csv(
        PROCESSED_DIR / "worldbank_prices_krw.csv", parse_dates=["date"]
    )

    # 관세청
    sources["customs"] = pd.read_csv(
        RAW_DIR / "customs" / "customs_import_prices.csv", parse_dates=["date"]
    )

    # ECOS
    sources["ecos"] = pd.read_csv(
        RAW_DIR / "ecos" / "ecos_ppi_cpi.csv", parse_dates=["date"]
    )

    # 환율
    sources["exchange_rate"] = pd.read_csv(
        RAW_DIR / "exchange_rate" / "exchange_rate_monthly.csv", parse_dates=["date"]
    )

    # KAMIS
    kamis_path = RAW_DIR / "kamis" / "kamis_wholesale_monthly.csv"
    if kamis_path.exists():
        sources["kamis"] = pd.read_csv(kamis_path, parse_dates=["date"])
    else:
        sources["kamis"] = pd.DataFrame()

    # FAO
    fao_path = RAW_DIR / "fao" / "fao_ffpi_monthly.csv"
    if fao_path.exists():
        sources["fao"] = pd.read_csv(fao_path, parse_dates=["date"])
    else:
        sources["fao"] = pd.DataFrame()

    # 공통 기간
    sources["common_periods"] = pd.read_csv(
        PROCESSED_DIR / "common_periods.csv",
        parse_dates=["common_start", "common_end"]
    )

    # 날짜 통일
    for key in ["worldbank", "customs", "ecos", "kamis", "exchange_rate", "fao"]:
        df = sources[key]
        if not df.empty and "date" in df.columns:
            df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()

    return sources


def interpolate_series(series):
    """선형 보간 + ffill/bfill로 양 끝 결측 처리"""
    result = series.interpolate(method="linear")
    result = result.ffill().bfill()
    return result


def merge_single_commodity(cid, commodity_config, sources):
    """단일 품목의 모든 소스를 하나의 DataFrame으로 merge"""
    has_wholesale = commodity_config.get("has_wholesale", False)

    # 공통 기간
    cp = sources["common_periods"]
    cp_row = cp[cp["commodity_id"] == cid]
    if cp_row.empty or cp_row.iloc[0]["common_months"] == 0:
        return pd.DataFrame()

    start = cp_row.iloc[0]["common_start"]
    end = cp_row.iloc[0]["common_end"]

    # 기간 내 월별 인덱스
    date_range = pd.date_range(start=start, end=end, freq="MS")
    result = pd.DataFrame({"date": date_range})

    # 1) 국제가 (원화 환산, 원/톤)
    wb = sources["worldbank"]
    wb_sub = wb[wb["commodity_id"] == cid][["date", "price_usd_mt", "price_krw_mt"]].copy()
    result = result.merge(wb_sub, on="date", how="left")
    result = result.rename(columns={
        "price_usd_mt": "intl_price_usd",
        "price_krw_mt": "intl_price_krw",
    })

    # 2) 환율
    exrate = sources["exchange_rate"][["date", "exchange_rate_avg"]].copy()
    result = result.merge(exrate, on="date", how="left")
    result = result.rename(columns={"exchange_rate_avg": "exchange_rate"})

    # 3) 수입단가 ($/톤)
    cu = sources["customs"]
    cu_sub = cu[cu["commodity_id"] == cid][["date", "import_unit_price"]].copy()
    result = result.merge(cu_sub, on="date", how="left")
    result = result.rename(columns={"import_unit_price": "import_price_usd"})

    # 4) PPI (지수, 2020=100)
    ecos = sources["ecos"]
    ppi = ecos[(ecos["commodity_id"] == cid) & (ecos["data_type"] == "ppi")]
    ppi_sub = ppi[["date", "value"]].copy()
    result = result.merge(ppi_sub, on="date", how="left")
    result = result.rename(columns={"value": "ppi"})

    # 5) CPI (지수, 2020=100)
    cpi = ecos[(ecos["commodity_id"] == cid) & (ecos["data_type"] == "cpi")]
    cpi_sub = cpi[["date", "value"]].copy()
    result = result.merge(cpi_sub, on="date", how="left")
    result = result.rename(columns={"value": "cpi"})

    # 6) KAMIS 도매가 (원/kg, 해당 품목만)
    if has_wholesale and not sources["kamis"].empty:
        kamis = sources["kamis"]
        kamis_sub = kamis[kamis["commodity_id"] == cid][["date", "price"]].copy()
        result = result.merge(kamis_sub, on="date", how="left")
        result = result.rename(columns={"price": "wholesale_price"})
    else:
        result["wholesale_price"] = np.nan

    # 7) 결측치 보간 (linear + ffill/bfill)
    value_cols = ["intl_price_usd", "intl_price_krw", "exchange_rate",
                  "import_price_usd", "ppi", "cpi", "wholesale_price"]
    for col in value_cols:
        if col in result.columns and result[col].notna().any():
            result[col] = interpolate_series(result[col])

    # 8) commodity_id 컬럼 추가
    result.insert(0, "commodity_id", cid)

    # 도매가 없는 품목은 wholesale_price 컬럼 제거
    if not has_wholesale and "wholesale_price" in result.columns:
        result = result.drop(columns=["wholesale_price"])

    return result


def merge_all_datasets():
    print("=" * 60)
    print("  Step 4: 품목별 통합 데이터셋 생성")
    print("=" * 60)

    sources = load_sources()

    # 매핑 파일
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

        # 개별 품목 CSV 저장
        item_path = MERGED_DIR / f"{cid}.csv"
        merged.to_csv(item_path, index=False, encoding="utf-8-sig")

        # 보간 후 남은 결측
        value_cols = [c for c in merged.columns if c not in ["date", "commodity_id"]]
        remaining_missing = merged[value_cols].isna().sum().sum()

        period_str = f"{merged['date'].min().strftime('%Y-%m')}~{merged['date'].max().strftime('%Y-%m')}"
        print(f"  {name_kr:<12} {period_str:<25} {len(merged):>5} {len(merged.columns):>5} {remaining_missing:>7}")

        all_merged.append(merged)

    # 전체 통합 CSV
    if all_merged:
        full_df = pd.concat(all_merged, ignore_index=True)
        full_path = MERGED_DIR / "all_commodities.csv"
        full_df.to_csv(full_path, index=False, encoding="utf-8-sig")
        print(f"\n  💾 전체 통합: {full_path} ({len(full_df)}행)")

    # 개별 파일 목록
    print(f"\n  💾 개별 품목 파일:")
    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        item_path = MERGED_DIR / f"{cid}.csv"
        if item_path.exists():
            print(f"    {item_path.name}")

    # 컬럼 설명
    print(f"\n  📋 통합 데이터셋 컬럼 설명:")
    print(f"    date             — 월 (YYYY-MM-01)")
    print(f"    commodity_id     — 품목 ID")
    print(f"    intl_price_usd   — 국제가 ($/톤)")
    print(f"    intl_price_krw   — 국제가 원화 환산 (원/톤)")
    print(f"    exchange_rate    — 월평균 환율 (원/달러)")
    print(f"    import_price_usd — 수입단가 ($/톤)")
    print(f"    ppi              — 생산자물가지수 (2020=100)")
    print(f"    cpi              — 소비자물가지수 (2020=100)")
    print(f"    wholesale_price  — KAMIS 도매가 (원/kg, 해당 품목만)")

    return full_df if all_merged else pd.DataFrame()


if __name__ == "__main__":
    merge_all_datasets()
