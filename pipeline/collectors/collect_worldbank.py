"""World Bank Pink Sheet에서 밀, 옥수수, 대두 월별 국제가격(USD) 수집."""

import os
import sys
import json
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "worldbank"
RAW_DIR.mkdir(parents=True, exist_ok=True)

PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


def download_pink_sheet():
    """Pink Sheet Excel 파일 다운로드. 이미 있으면 재사용."""
    output_path = RAW_DIR / "CMO-Historical-Data-Monthly.xlsx"

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  이미 다운로드됨: {output_path.name} ({size_mb:.1f}MB)")
        return output_path

    print(f"  다운로드 중: {PINK_SHEET_URL}")

    try:
        resp = requests.get(PINK_SHEET_URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"  다운로드 실패: {e}")
        print(f"  수동 다운로드 후 {output_path}에 저장 필요")
        print("  URL: https://www.worldbank.org/en/research/commodity-markets")
        return None
    
    with open(output_path, "wb") as f:
        f.write(resp.content)
    
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  다운로드 완료: {output_path.name} ({size_mb:.1f}MB)")
    return output_path


def parse_pink_sheet(excel_path):
    """Pink Sheet Excel에서 품목별 월별 가격 추출.

    행4 = 품목명 헤더, 행6~ = 데이터. 날짜 컬럼이 첫 번째.
    """
    print(f"\n  Excel 파싱 중: {excel_path.name}")
    
    # 시트명 확인
    xls = pd.ExcelFile(excel_path)
    sheet_names = xls.sheet_names
    print(f"  시트 목록: {sheet_names}")
    
    target_sheet = None
    for name in sheet_names:
        if "monthly" in name.lower() and "price" in name.lower():
            target_sheet = name
            break

    if target_sheet is None:
        target_sheet = sheet_names[0]
        print(f"  'Monthly Prices' 시트 미발견, '{target_sheet}' 사용")
    else:
        print(f"  타겟 시트: {target_sheet}")

    header_row = 4

    df = pd.read_excel(excel_path, sheet_name=target_sheet, header=header_row)
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    
    print(f"  전체 컬럼 수: {len(df.columns)}, 행 수: {len(df)}")

    date_col = df.columns[0]
    print(f"  날짜 컬럼: '{date_col}'")

    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    column_map = {}
    
    if mapping_path.exists():
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        for commodity in mapping.get("commodities", []):
            cid = commodity["commodity_id"]
            wb = commodity.get("sources", {}).get("worldbank_pinksheet", {})
            if wb.get("status") == "confirmed" and wb.get("column_name"):
                column_map[cid] = wb["column_name"]
    
    if not column_map:
        column_map = {
            "wheat": "Wheat, US HRW",
            "maize": "Maize",
            "soybean": "Soybeans",
        }
    
    print("\n  찾을 품목 컬럼:")
    for cid, col_name in column_map.items():
        print(f"    {cid}: '{col_name}'")
    
    # 정확 일치, 부분 포함, 키워드 순으로 컬럼 매칭
    matched_columns = {}
    for cid, target_name in column_map.items():
        exact = [c for c in df.columns if c == target_name]
        if exact:
            matched_columns[cid] = exact[0]
            continue

        partial = [c for c in df.columns if target_name.lower() in c.lower()]
        if partial:
            matched_columns[cid] = partial[0]
            continue

        keywords = target_name.lower().split(",")[0].split()
        keyword_match = [c for c in df.columns if all(kw in c.lower() for kw in keywords)]
        if keyword_match:
            matched_columns[cid] = keyword_match[0]
            continue

        print(f"    '{target_name}' 매칭 실패")

    if not matched_columns:
        print("\n  품목 컬럼을 찾을 수 없습니다.")
        for c in df.columns[:30]:
            print(f"    - {c}")
        return pd.DataFrame()

    print("\n  매칭된 컬럼:")
    for cid, col in matched_columns.items():
        print(f"    {cid}: '{col}'")
    
    records = []
    for cid, col in matched_columns.items():
        subset = df[[date_col, col]].copy()
        subset.columns = ["date_raw", "value"]

        subset = subset.dropna(subset=["value"])
        subset = subset[subset["value"] != ".."]
        subset = subset[subset["value"] != "…"]

        subset["date"] = pd.to_datetime(
            subset["date_raw"].astype(str).str.replace("M", "-"),
            format="%Y-%m",
            errors="coerce"
        )

        subset["value"] = pd.to_numeric(subset["value"], errors="coerce")
        subset = subset.dropna(subset=["value"])

        subset = subset[subset["date"] >= "2000-01-01"]
        # $/kg 단위 품목은 $/mt로 변환
        kg_items = {"coffee", "banana", "orange", "beef", "sugar"}
        if cid in kg_items:
            subset["value"] = subset["value"] * 1000
        
        for _, row in subset.iterrows():
            records.append({
                "date": row["date"],
                "commodity_id": cid,
                "price_usd_mt": row["value"],
                "source_column": col,
            })
    
    result = pd.DataFrame(records)
    if not result.empty:
        result = result.sort_values(["commodity_id", "date"]).reset_index(drop=True)
    
    return result


def collect_worldbank():
    """World Bank Pink Sheet 전체 수집."""
    print("=" * 60)
    print("  World Bank Pink Sheet 수집")
    print("=" * 60)

    excel_path = download_pink_sheet()
    if excel_path is None:
        return pd.DataFrame()

    df = parse_pink_sheet(excel_path)

    if df.empty:
        print("\n  추출된 데이터가 없습니다.")
        return df

    output_path = RAW_DIR / "worldbank_prices.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  저장 완료: {output_path}")

    print("\n  수집 요약:")
    summary = df.groupby("commodity_id").agg(
        months=("date", "count"),
        start=("date", "min"),
        end=("date", "max"),
        price_min=("price_usd_mt", "min"),
        price_max=("price_usd_mt", "max"),
        price_last=("price_usd_mt", "last"),
    )
    for cid, row in summary.iterrows():
        print(
            f"    {cid:<10} {row['months']:>4}개월  "
            f"{row['start'].strftime('%Y-%m')}~{row['end'].strftime('%Y-%m')}  "
            f"${row['price_min']:.0f}~${row['price_max']:.0f}/mt  "
            f"(최근 ${row['price_last']:.0f})"
        )
    
    return df


if __name__ == "__main__":
    collect_worldbank()
