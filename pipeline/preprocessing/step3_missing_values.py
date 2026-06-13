"""Step 3: 결측치 분석 및 선형 보간. 결측률 10% 이상 품목 플래그."""

import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_common_periods():
    """Step 2 산출 공통 기간 로드."""
    cp_path = PROCESSED_DIR / "common_periods.csv"
    if not cp_path.exists():
        print("  ❌ common_periods.csv 없음. Step 2를 먼저 실행하세요.")
        return None
    df = pd.read_csv(cp_path, parse_dates=["common_start", "common_end"])
    return df


def find_consecutive_missing(series, threshold=3):
    """threshold 이상 연속 NaN 구간의 (시작, 종료, 길이) 반환."""
    is_null = series.isna()
    groups = []
    count = 0
    start_idx = None

    for i, val in enumerate(is_null):
        if val:
            if count == 0:
                start_idx = i
            count += 1
        else:
            if count >= threshold:
                groups.append((start_idx, i - 1, count))
            count = 0
            start_idx = None

    if count >= threshold:
        groups.append((start_idx, len(is_null) - 1, count))

    return groups


def check_missing_values():
    print("=" * 60)
    print("  Step 3: 결측치 처리")
    print("=" * 60)

    common_periods = load_common_periods()
    if common_periods is None:
        return

    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    wb = pd.read_csv(PROCESSED_DIR / "worldbank_prices_krw.csv", parse_dates=["date"])
    customs = pd.read_csv(RAW_DIR / "customs" / "customs_import_prices.csv", parse_dates=["date"])
    ecos = pd.read_csv(RAW_DIR / "ecos" / "ecos_ppi_cpi.csv", parse_dates=["date"])

    kamis_path = RAW_DIR / "kamis" / "kamis_wholesale_monthly.csv"
    kamis = pd.read_csv(kamis_path, parse_dates=["date"]) if kamis_path.exists() else pd.DataFrame()

    for df in [wb, customs, ecos, kamis]:
        if not df.empty and "date" in df.columns:
            df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()

    all_reports = []
    excluded_items = []
    flagged_gaps = []

    print(f"\n  {'품목':<12} {'소스':<10} {'기간내총월':>8} {'결측':>5} {'결측률':>7} {'보간후결측':>8} {'상태'}")
    print(f"  {'─'*75}")

    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        name_kr = commodity["name_kr"]
        has_wholesale = commodity.get("has_wholesale", False)

        cp_row = common_periods[common_periods["commodity_id"] == cid]
        if cp_row.empty or cp_row.iloc[0]["common_months"] == 0:
            print(f"  {name_kr:<12} 공통 기간 없음, 건너뜀")
            continue

        start = cp_row.iloc[0]["common_start"]
        end = cp_row.iloc[0]["common_end"]

        date_range = pd.date_range(start=start, end=end, freq="MS")
        total_months = len(date_range)

        source_checks = []

        wb_sub = wb[(wb["commodity_id"] == cid) & (wb["date"].isin(date_range))]
        wb_full = pd.DataFrame({"date": date_range}).merge(
            wb_sub[["date", "price_krw_mt"]], on="date", how="left"
        )
        source_checks.append(("국제가(원화)", wb_full, "price_krw_mt"))

        cu_sub = customs[(customs["commodity_id"] == cid) & (customs["date"].isin(date_range))]
        cu_full = pd.DataFrame({"date": date_range}).merge(
            cu_sub[["date", "import_unit_price"]], on="date", how="left"
        )
        source_checks.append(("수입단가", cu_full, "import_unit_price"))

        ppi_sub = ecos[
            (ecos["commodity_id"] == cid) &
            (ecos["data_type"] == "ppi") &
            (ecos["date"].isin(date_range))
        ]
        ppi_full = pd.DataFrame({"date": date_range}).merge(
            ppi_sub[["date", "value"]], on="date", how="left"
        )
        source_checks.append(("PPI", ppi_full, "value"))

        cpi_sub = ecos[
            (ecos["commodity_id"] == cid) &
            (ecos["data_type"] == "cpi") &
            (ecos["date"].isin(date_range))
        ]
        cpi_full = pd.DataFrame({"date": date_range}).merge(
            cpi_sub[["date", "value"]], on="date", how="left"
        )
        source_checks.append(("CPI", cpi_full, "value"))

        if has_wholesale and not kamis.empty:
            kamis_sub = kamis[(kamis["commodity_id"] == cid) & (kamis["date"].isin(date_range))]
            kamis_full = pd.DataFrame({"date": date_range}).merge(
                kamis_sub[["date", "price"]], on="date", how="left"
            )
            source_checks.append(("KAMIS", kamis_full, "price"))

        for source_name, df, value_col in source_checks:
            missing_before = df[value_col].isna().sum()
            missing_rate = missing_before / total_months * 100

            consec_gaps = find_consecutive_missing(df[value_col], threshold=3)

            df[f"{value_col}_interpolated"] = df[value_col].interpolate(method="linear")
            missing_after = df[f"{value_col}_interpolated"].isna().sum()

            if missing_rate >= 10:
                status = "❌ 제외 대상"
                excluded_items.append({
                    "commodity_id": cid,
                    "name_kr": name_kr,
                    "source": source_name,
                    "missing_rate": missing_rate,
                })
            elif consec_gaps:
                status = f"⚠️ 연속결측 {len(consec_gaps)}건"
                for gap_start, gap_end, gap_len in consec_gaps:
                    flagged_gaps.append({
                        "commodity_id": cid,
                        "name_kr": name_kr,
                        "source": source_name,
                        "gap_start": df.iloc[gap_start]["date"].strftime("%Y-%m"),
                        "gap_end": df.iloc[gap_end]["date"].strftime("%Y-%m"),
                        "gap_months": gap_len,
                    })
            else:
                status = "✅ 정상"

            print(
                f"  {name_kr:<12} {source_name:<10} {total_months:>8} "
                f"{missing_before:>5} {missing_rate:>6.1f}% {missing_after:>8}  {status}"
            )

            all_reports.append({
                "commodity_id": cid,
                "name_kr": name_kr,
                "source": source_name,
                "total_months": total_months,
                "missing_before": missing_before,
                "missing_rate_pct": round(missing_rate, 1),
                "missing_after_interpolation": missing_after,
                "consecutive_gaps": len(consec_gaps),
                "status": status,
            })

        print()

    print(f"  {'='*60}")
    print(f"  📋 결측치 처리 요약")
    print(f"  {'='*60}")

    report_df = pd.DataFrame(all_reports)
    total_series = len(report_df)
    clean = len(report_df[report_df["missing_before"] == 0])
    has_missing = len(report_df[report_df["missing_before"] > 0])

    print(f"  전체 시계열: {total_series}개")
    print(f"  결측 0건: {clean}개")
    print(f"  결측 있음: {has_missing}개")

    if excluded_items:
        print(f"\n  ❌ 결측률 10% 이상 (분석 제외 대상):")
        for item in excluded_items:
            print(f"    {item['name_kr']} / {item['source']}: {item['missing_rate']:.1f}%")
    else:
        print(f"\n  ✅ 결측률 10% 이상 품목 없음")

    if flagged_gaps:
        print(f"\n  ⚠️ 연속 결측 3개월 이상 구간:")
        for gap in flagged_gaps:
            print(f"    {gap['name_kr']} / {gap['source']}: {gap['gap_start']}~{gap['gap_end']} ({gap['gap_months']}개월)")
    else:
        print(f"\n  ✅ 연속 결측 3개월 이상 구간 없음")

    report_path = PROCESSED_DIR / "missing_value_report.csv"
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장: {report_path}")

    return report_df


if __name__ == "__main__":
    check_missing_values()
