"""Step 5: 품목별 분석 메타데이터(공통 기간, 구간 페어)를 수집해 product_config.json을 생성한다."""

import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def generate_product_config():
    print("=" * 60)
    print("  Step 5: PRODUCT_CONFIG 생성")
    print("=" * 60)

    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    cp = pd.read_csv(
        PROCESSED_DIR / "common_periods.csv",
        parse_dates=["common_start", "common_end"]
    )

    config = {}

    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        name_kr = commodity["name_kr"]
        has_wholesale = commodity.get("has_wholesale", False)

        cp_row = cp[cp["commodity_id"] == cid]
        if cp_row.empty or cp_row.iloc[0]["common_months"] == 0:
            continue

        common_start = cp_row.iloc[0]["common_start"].strftime("%Y-%m")
        common_end = cp_row.iloc[0]["common_end"].strftime("%Y-%m")
        common_months = int(cp_row.iloc[0]["common_months"])

        segments = ["A", "B", "C", "D"] if has_wholesale else ["A", "B", "D_prime"]

        ppi_info = commodity.get("sources", {}).get("ecos_ppi", {})
        cpi_info = commodity.get("sources", {}).get("ecos_cpi", {})

        config[cid] = {
            "name_kr": name_kr,
            "name_en": commodity.get("name_en", ""),
            "has_wholesale": has_wholesale,
            "segments": segments,
            "common_start": common_start,
            "common_end": common_end,
            "common_months": common_months,
            "ppi": {
                "stat_code": ppi_info.get("stat_code", ""),
                "item_code": ppi_info.get("item_code", ""),
                "item_name": ppi_info.get("item_name", ""),
            },
            "cpi": {
                "stat_code": cpi_info.get("stat_code", ""),
                "item_code": cpi_info.get("item_code", ""),
                "item_name": cpi_info.get("item_name", ""),
            },
            "segment_pairs": {},
        }

        pairs = {
            "A": ("intl_price_krw", "import_price_usd"),
            "B": ("import_price_usd", "ppi"),
        }
        if has_wholesale:
            pairs["C"] = ("ppi", "wholesale_price")
            pairs["D"] = ("wholesale_price", "cpi")
        else:
            pairs["D_prime"] = ("ppi", "cpi")

        config[cid]["segment_pairs"] = pairs

    config_path = PROCESSED_DIR / "product_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 저장: {config_path}")

    print(f"\n  {'품목':<12} {'구간':<18} {'기간':<25} {'월수':>5} {'도매가'}")
    print(f"  {'─'*75}")

    for cid, cfg in config.items():
        segments_str = ", ".join(cfg["segments"])
        period_str = f"{cfg['common_start']}~{cfg['common_end']}"
        wholesale_str = "✅" if cfg["has_wholesale"] else "없음"
        print(f"  {cfg['name_kr']:<12} {segments_str:<18} {period_str:<25} {cfg['common_months']:>5} {wholesale_str}")

    b2b = [cid for cid, cfg in config.items() if not cfg["has_wholesale"]]
    wholesale = [cid for cid, cfg in config.items() if cfg["has_wholesale"]]

    print(f"\n  📋 품목 그룹 요약:")
    print(f"    B2B 직납형 (A-B-D 구간): {len(b2b)}개 - {', '.join(b2b)}")
    print(f"    도매 경유  (A-B-C-D 구간): {len(wholesale)}개 - {', '.join(wholesale)}")

    return config


if __name__ == "__main__":
    generate_product_config()
