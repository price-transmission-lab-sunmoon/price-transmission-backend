"""관세청 수출입 실적 Excel → 품목별 월별 수입단가($/톤) 파서.

data/raw/customs/customs_YYYY_YYYY.xlsx 파일을 파싱해 통합 CSV 생성.
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "customs"
RAW_DIR.mkdir(parents=True, exist_ok=True)

HS_TO_COMMODITY = {
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


def parse_single_excel(filepath):
    """관세청 수출입 실적 Excel 1개 파일 파싱.

    행4=헤더, 행5=총계, 행6~=데이터. 단위: 중량 kg, 금액 천 달러.
    """
    print(f"    파싱 중: {filepath.name}")
    
    # 헤더 행 찾기 (기간, HS코드 등이 있는 행)
    df_raw = pd.read_excel(filepath, header=None, nrows=10)
    
    header_row = None
    for i in range(10):
        row_text = " ".join(str(v) for v in df_raw.iloc[i].tolist()).lower()
        if "기간" in row_text and ("hs" in row_text or "코드" in row_text):
            header_row = i
            break
    
    if header_row is None:
        header_row = 4
        print(f"      헤더 자동 탐지 실패, 행 {header_row}로 시도")
    
    # 데이터 읽기
    df = pd.read_excel(filepath, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower().replace(" ", "")
        if "기간" in col:
            col_mapping[col] = "period"
        elif "hs" in col_lower or "코드" in col_lower:
            col_mapping[col] = "hs_code"
        elif "품목" in col:
            col_mapping[col] = "item_name"
        elif "수입" in col and "중량" in col:
            col_mapping[col] = "import_weight"
        elif "수입" in col and "금액" in col:
            col_mapping[col] = "import_value"
        elif "수출" in col and "중량" in col:
            col_mapping[col] = "export_weight"
        elif "수출" in col and "금액" in col:
            col_mapping[col] = "export_value"
    
    df = df.rename(columns=col_mapping)
    
    required = ["period", "hs_code", "import_weight", "import_value"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"      필수 컬럼 누락: {missing}")
        print(f"      현재 컬럼: {list(df.columns)}")
        return pd.DataFrame()

    # 총계 행 제거 (YYYY.MM 형식만 유지)
    df = df[df["period"].astype(str).str.match(r"^\d{4}\.\d{2}$", na=False)].copy()

    # float 1001.0 → "1001" (4자리 zero-padding)
    df["hs_code"] = df["hs_code"].apply(
        lambda x: str(int(x)).zfill(4) if pd.notna(x) and str(x) != 'nan' else ""
    )
    
    target_hs = set(HS_TO_COMMODITY.keys())
    df = df[df["hs_code"].isin(target_hs)].copy()

    if df.empty:
        print("      대상 HS코드 데이터 없음")
        return df

    for col in ["import_weight", "import_value"]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", "").str.strip(),
            errors="coerce"
        ).fillna(0)

    df["date"] = pd.to_datetime(
        df["period"].str.replace(".", "-") + "-01",
        format="%Y-%m-%d",
        errors="coerce"
    )
    
    df["commodity_id"] = df["hs_code"].map(HS_TO_COMMODITY)

    # 수입단가($/톤) = 금액(천달러) × 1,000,000 ÷ 중량(kg)
    df["import_unit_price"] = None
    mask = df["import_weight"] > 0
    df.loc[mask, "import_unit_price"] = (
        df.loc[mask, "import_value"] * 1_000_000 / df.loc[mask, "import_weight"]
    )
    result = df[[
        "date", "commodity_id", "hs_code",
        "import_weight", "import_value", "import_unit_price" 
    ]].copy()
    
    result = result.dropna(subset=["date"])

    print(f"      {len(result)}행 추출")
    return result


def parse_all_customs():
    """data/raw/customs/ 폴더의 모든 Excel 파일을 파싱해 통합."""
    print("=" * 60)
    print("  관세청 수입단가 파싱")
    print("=" * 60)

    excel_files = sorted(RAW_DIR.glob("customs_*.xlsx"))
    if not excel_files:
        excel_files = sorted(RAW_DIR.glob("*.xlsx"))
    
    if not excel_files:
        print("  data/raw/customs/ 폴더에 Excel 파일이 없습니다.")
        return pd.DataFrame()
    
    print(f"  발견된 파일: {len(excel_files)}개")
    
    all_dfs = []
    for filepath in excel_files:
        df = parse_single_excel(filepath)
        if not df.empty:
            all_dfs.append(df)
    
    if not all_dfs:
        print("\n  파싱된 데이터가 없습니다.")
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True)
    # beef: 0201+0202 같은 월 합산 후 단가 재계산
    beef = result[result["commodity_id"] == "beef"]
    others = result[result["commodity_id"] != "beef"]
    
    if not beef.empty:
        beef_merged = beef.groupby(["date", "commodity_id"]).agg(
            hs_code=("hs_code", "first"),
            import_weight=("import_weight", "sum"),
            import_value=("import_value", "sum"),
        ).reset_index()
        beef_merged["hs_code"] = "0201-0202"
        mask = beef_merged["import_weight"] > 0
        beef_merged["import_unit_price"] = None
        beef_merged.loc[mask, "import_unit_price"] = (
            beef_merged.loc[mask, "import_value"] * 1_000_000 / beef_merged.loc[mask, "import_weight"]
        )
        result = pd.concat([others, beef_merged], ignore_index=True)
    
    result = result.drop_duplicates(subset=["date", "commodity_id"])
    result = result.sort_values(["commodity_id", "date"]).reset_index(drop=True)

    output_path = RAW_DIR / "customs_import_prices.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  저장 완료: {output_path}")

    print("\n  수집 요약:")
    for cid in sorted(result["commodity_id"].unique()):
        sub = result[result["commodity_id"] == cid]
        valid = sub["import_unit_price"].dropna()
        
        if valid.empty:
            print(f"    {cid:<10} {len(sub):>4}개월  수입단가 산출 불가")
            continue
        
        print(
            f"    {cid:<10} {len(sub):>4}개월  "
            f"{sub['date'].min().strftime('%Y-%m')}~{sub['date'].max().strftime('%Y-%m')}  "
            f"${valid.min():.0f}~${valid.max():.0f}/톤  "
            f"(최근 ${valid.iloc[-1]:.0f})"
        )
    
    zero_weight = result[result["import_weight"] == 0]
    if not zero_weight.empty:
        print(f"\n  수입중량 0인 월: {len(zero_weight)}건")
        for _, row in zero_weight.iterrows():
            print(f"     {row['date'].strftime('%Y-%m')} {row['commodity_id']} (HS {row['hs_code']})")
    
    return result


if __name__ == "__main__":
    parse_all_customs()
