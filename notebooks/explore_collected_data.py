"""수집 데이터 탐색. 소스별 기간, 결측치 현황 및 품목별 가격 시각화."""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_all_data():
    """수집된 CSV 로드."""
    data = {}

    ecos_path = PROJECT_ROOT / "data" / "raw" / "ecos" / "ecos_ppi_cpi.csv"
    if ecos_path.exists():
        data["ecos"] = pd.read_csv(ecos_path, parse_dates=["date"])
        print(f"  ✅ ECOS: {len(data['ecos'])}행")
    else:
        print(f"  ❌ ECOS 파일 없음: {ecos_path}")

    wb_path = PROJECT_ROOT / "data" / "raw" / "worldbank" / "worldbank_prices.csv"
    if wb_path.exists():
        data["worldbank"] = pd.read_csv(wb_path, parse_dates=["date"])
        print(f"  ✅ World Bank: {len(data['worldbank'])}행")
    else:
        print(f"  ❌ World Bank 파일 없음: {wb_path}")

    customs_path = PROJECT_ROOT / "data" / "raw" / "customs" / "customs_import_prices.csv"
    if customs_path.exists():
        data["customs"] = pd.read_csv(customs_path, parse_dates=["date"])
        print(f"  ✅ 관세청: {len(data['customs'])}행")
    else:
        print(f"  ❌ 관세청 파일 없음: {customs_path}")

    exrate_path = PROJECT_ROOT / "data" / "raw" / "exchange_rate" / "exchange_rate_monthly.csv"
    if exrate_path.exists():
        data["exchange_rate"] = pd.read_csv(exrate_path, parse_dates=["date"])
        print(f"  ✅ 환율: {len(data['exchange_rate'])}행")
    else:
        print(f"  ⏳ 환율 파일 없음 (수집 진행 중)")

    return data


def analyze_coverage(data):
    """소스별 품목별 기간, 결측치 현황."""
    print(f"\n{'='*70}")
    print(f"  소스별 데이터 현황")
    print(f"{'='*70}")

    coverage = []

    if "ecos" in data:
        df = data["ecos"]
        for (cid, dtype), grp in df[df["data_type"].isin(["ppi", "cpi"])].groupby(["commodity_id", "data_type"]):
            coverage.append({
                "source": "ECOS",
                "commodity": cid,
                "type": dtype.upper(),
                "item": grp["item_name"].iloc[0],
                "start": grp["date"].min(),
                "end": grp["date"].max(),
                "months": len(grp),
                "missing": grp["value"].isna().sum(),
            })

    if "worldbank" in data:
        df = data["worldbank"]
        for cid, grp in df.groupby("commodity_id"):
            coverage.append({
                "source": "World Bank",
                "commodity": cid,
                "type": "국제가(USD)",
                "item": grp["source_column"].iloc[0],
                "start": grp["date"].min(),
                "end": grp["date"].max(),
                "months": len(grp),
                "missing": grp["price_usd_mt"].isna().sum(),
            })

    if "customs" in data:
        df = data["customs"]
        for cid, grp in df.groupby("commodity_id"):
            coverage.append({
                "source": "관세청",
                "commodity": cid,
                "type": "수입단가($/톤)",
                "item": f"HS {grp['hs_code'].iloc[0]}",
                "start": grp["date"].min(),
                "end": grp["date"].max(),
                "months": len(grp),
                "missing": grp["import_unit_price"].isna().sum(),
            })

    if "exchange_rate" in data:
        df = data["exchange_rate"]
        coverage.append({
            "source": "수출입은행",
            "commodity": "공통",
            "type": "환율(원/달러)",
            "item": "USD/KRW",
            "start": df["date"].min(),
            "end": df["date"].max(),
            "months": len(df),
            "missing": df["exchange_rate_avg"].isna().sum(),
        })

    cov_df = pd.DataFrame(coverage)

    print(f"\n  {'소스':<12} {'품목':<10} {'유형':<15} {'항목':<18} {'시작':>8} {'종료':>8} {'월수':>5} {'결측':>4}")
    print(f"  {'-'*90}")
    for _, row in cov_df.iterrows():
        print(
            f"  {row['source']:<12} {row['commodity']:<10} {row['type']:<15} {row['item']:<18} "
            f"{row['start'].strftime('%Y-%m'):>8} {row['end'].strftime('%Y-%m'):>8} "
            f"{row['months']:>5} {row['missing']:>4}"
        )

    return cov_df


def find_common_period(data):
    """품목별 소스 교집합 기간 산출."""
    print(f"\n{'='*70}")
    print(f"  품목별 공통 분석 가능 기간")
    print(f"{'='*70}")

    commodities = ["wheat", "maize", "soybean"]

    for cid in commodities:
        starts = []
        ends = []

        if "worldbank" in data:
            wb = data["worldbank"][data["worldbank"]["commodity_id"] == cid]
            if not wb.empty:
                starts.append(wb["date"].min())
                ends.append(wb["date"].max())

        if "customs" in data:
            cu = data["customs"][data["customs"]["commodity_id"] == cid]
            if not cu.empty:
                starts.append(cu["date"].min())
                ends.append(cu["date"].max())

        if "ecos" in data:
            ppi = data["ecos"][(data["ecos"]["commodity_id"] == cid) & (data["ecos"]["data_type"] == "ppi")]
            if not ppi.empty:
                starts.append(ppi["date"].min())
                ends.append(ppi["date"].max())

        if "ecos" in data:
            cpi = data["ecos"][(data["ecos"]["commodity_id"] == cid) & (data["ecos"]["data_type"] == "cpi")]
            if not cpi.empty:
                starts.append(cpi["date"].min())
                ends.append(cpi["date"].max())

        if starts and ends:
            common_start = max(starts)
            common_end = min(ends)
            months = (common_end.year - common_start.year) * 12 + common_end.month - common_start.month + 1
            print(f"  {cid:<10} {common_start.strftime('%Y-%m')} ~ {common_end.strftime('%Y-%m')}  ({months}개월)")
        else:
            print(f"  {cid:<10} 데이터 부족")


def plot_price_series(data):
    """품목별 국제가, 수입단가, PPI/CPI 3열 시각화."""
    print(f"\n{'='*70}")
    print(f"  시각화 생성 중...")
    print(f"{'='*70}")

    commodities = {
        "wheat": {"kr": "밀", "ppi": "제분", "cpi": "밀가루"},
        "maize": {"kr": "옥수수", "ppi": "사료", "cpi": "돼지고기"},
        "soybean": {"kr": "대두", "ppi": "유지", "cpi": "식용유"},
    }

    fig, axes = plt.subplots(3, 3, figsize=(18, 12))

    for row_idx, (cid, info) in enumerate(commodities.items()):
        ax = axes[row_idx][0]
        if "worldbank" in data:
            wb = data["worldbank"][data["worldbank"]["commodity_id"] == cid].sort_values("date")
            if not wb.empty:
                ax.plot(wb["date"], wb["price_usd_mt"], color="tab:blue", linewidth=1)
        ax.set_title(f"{info['kr']} 국제가 ($/톤)")
        ax.set_ylabel("$/톤")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

        ax = axes[row_idx][1]
        if "customs" in data:
            cu = data["customs"][data["customs"]["commodity_id"] == cid].sort_values("date")
            if not cu.empty:
                ax.plot(cu["date"], cu["import_unit_price"], color="tab:orange", linewidth=1)
        ax.set_title(f"{info['kr']} 수입단가 ($/톤)")
        ax.set_ylabel("$/톤")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

        ax = axes[row_idx][2]
        if "ecos" in data:
            ppi = data["ecos"][(data["ecos"]["commodity_id"] == cid) & (data["ecos"]["data_type"] == "ppi")].sort_values("date")
            cpi = data["ecos"][(data["ecos"]["commodity_id"] == cid) & (data["ecos"]["data_type"] == "cpi")].sort_values("date")
            if not ppi.empty:
                ax.plot(ppi["date"], ppi["value"], color="tab:green", linewidth=1, label=f"PPI ({info['ppi']})")
            if not cpi.empty:
                ax.plot(cpi["date"], cpi["value"], color="tab:red", linewidth=1, label=f"CPI ({info['cpi']})")
            ax.legend(fontsize=8)
        ax.set_title(f"{info['kr']} PPI / CPI (2020=100)")
        ax.set_ylabel("지수")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.suptitle("Phase 0 수집 데이터 탐색. 품목별 가격 전달 체계", fontsize=14, fontweight="bold")
    plt.tight_layout()

    chart_path = OUTPUT_DIR / "explore_collected_data.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"  💾 차트 저장: {chart_path}")
    plt.show()


def plot_overlay_comparison(data):
    """국제가 vs 수입단가 오버레이 비교."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    commodities = {
        "wheat": "밀",
        "maize": "옥수수",
        "soybean": "대두",
    }

    for idx, (cid, kr_name) in enumerate(commodities.items()):
        ax = axes[idx]

        if "worldbank" in data:
            wb = data["worldbank"][data["worldbank"]["commodity_id"] == cid].sort_values("date")
            if not wb.empty:
                ax.plot(wb["date"], wb["price_usd_mt"], color="tab:blue", linewidth=1, label="국제가 (World Bank)")

        if "customs" in data:
            cu = data["customs"][data["customs"]["commodity_id"] == cid].sort_values("date")
            if not cu.empty:
                ax.plot(cu["date"], cu["import_unit_price"], color="tab:orange", linewidth=1, alpha=0.8, label="수입단가 (관세청)")

        ax.set_title(f"{kr_name} 국제가 vs 수입단가 ($/톤)")
        ax.set_ylabel("$/톤")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.suptitle("국제가에서 수입단가로의 전달 추이", fontsize=13, fontweight="bold")
    plt.tight_layout()

    chart_path = OUTPUT_DIR / "explore_segment_A_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"  💾 차트 저장: {chart_path}")
    plt.show()


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Phase 0 수집 데이터 탐색 분석                          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    print(f"\n  📂 데이터 로드:")
    data = load_all_data()

    cov_df = analyze_coverage(data)

    find_common_period(data)

    plot_price_series(data)
    plot_overlay_comparison(data)

    print(f"\n  ✅ 탐색 분석 완료!")
    print(f"     차트 저장 위치: data/output/")
