"""Step 1: World Bank 달러 가격에 월평균 환율을 곱해 원화 환산 국제가(원/톤)를 산출한다."""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def convert_to_krw():
    print("=" * 60)
    print("  Step 1: 국제가 원화 환산")
    print("=" * 60)

    wb_path = RAW_DIR / "worldbank" / "worldbank_prices.csv"
    wb = pd.read_csv(wb_path, parse_dates=["date"])
    print(f"\n  World Bank: {len(wb)}행, {wb['commodity_id'].nunique()}개 품목")

    exrate_path = RAW_DIR / "exchange_rate" / "exchange_rate_monthly.csv"
    exrate = pd.read_csv(exrate_path, parse_dates=["date"])
    print(f"  환율: {len(exrate)}개월")

    wb["date"] = wb["date"].dt.to_period("M").dt.to_timestamp()
    exrate["date"] = exrate["date"].dt.to_period("M").dt.to_timestamp()

    merged = wb.merge(
        exrate[["date", "exchange_rate_avg"]],
        on="date",
        how="left"
    )

    missing_rate = merged["exchange_rate_avg"].isna().sum()
    if missing_rate > 0:
        print(f"\n  ⚠️ 환율 매칭 안 되는 행: {missing_rate}건")
        missing_dates = merged[merged["exchange_rate_avg"].isna()]["date"].unique()
        print(f"     기간: {missing_dates[0]} ~ {missing_dates[-1]}")

    merged["price_krw_mt"] = merged["price_usd_mt"] * merged["exchange_rate_avg"]

    output = merged[["date", "commodity_id", "price_usd_mt", "exchange_rate_avg", "price_krw_mt"]].copy()
    output = output.sort_values(["commodity_id", "date"]).reset_index(drop=True)

    output_path = PROCESSED_DIR / "worldbank_prices_krw.csv"
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장: {output_path}")

    print(f"\n  📋 품목별 원화 환산 요약:")
    for cid in sorted(output["commodity_id"].unique()):
        sub = output[output["commodity_id"] == cid]
        valid = sub.dropna(subset=["price_krw_mt"])
        missing = len(sub) - len(valid)
        if valid.empty:
            print(f"    {cid:<12} ❌ 환산 불가")
            continue
        print(
            f"    {cid:<12} {len(valid):>4}개월  "
            f"{valid['date'].min().strftime('%Y-%m')}~{valid['date'].max().strftime('%Y-%m')}  "
            f"{valid['price_krw_mt'].min():,.0f}~{valid['price_krw_mt'].max():,.0f} 원/톤  "
            f"(결측 {missing}건)"
        )

    return output


if __name__ == "__main__":
    convert_to_krw()
