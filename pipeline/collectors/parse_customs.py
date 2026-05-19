"""
관세청 수입단가 파서
==============================================
수집 대상: HS 1001(밀), 1005(옥수수), 1201(대두) 월별 수입단가
실행 방법: python src/collectors/parse_customs.py

data/raw/customs/ 폴더에 있는 Excel 파일들을 파싱하여
품목별 월별 수입단가($/톤)를 산출합니다.

파일 명명 규칙: customs_YYYY_YYYY.xlsx (예: customs_2000_2004.xlsx)
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

# HS코드 → 품목 매핑
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
    """
    관세청 수출입 실적 Excel 1개 파일 파싱
    
    Excel 구조 (확인된 구조):
    - 행 0~3: 제목, 검색조건 등 메타데이터
    - 행 4: 헤더 (기간, HS코드, 품목명, 수출중량, 수출금액, 수입중량, 수입금액, 무역수지)
    - 행 5: 총계
    - 행 6~: 데이터
    - 단위: 중량 kg, 금액 천 달러
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
        # 기본값: 행 4
        header_row = 4
        print(f"      ⚠️ 헤더 자동 탐지 실패, 행 {header_row}로 시도")
    
    # 데이터 읽기
    df = pd.read_excel(filepath, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    
    # 컬럼명 표준화 (다양한 형태 대응)
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
    
    # 필수 컬럼 확인
    required = ["period", "hs_code", "import_weight", "import_value"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"      ❌ 필수 컬럼 누락: {missing}")
        print(f"      현재 컬럼: {list(df.columns)}")
        return pd.DataFrame()
    
    # 총계 행 제거
    df = df[df["period"].astype(str).str.match(r"^\d{4}\.\d{2}$", na=False)].copy()
    
    # HS코드 변환 (float 1001.0 → 문자열 "1001", 4자리 zero-padding)
    df["hs_code"] = df["hs_code"].apply(
        lambda x: str(int(x)).zfill(4) if pd.notna(x) and str(x) != 'nan' else ""
    )
    
    # 우리가 필요한 HS코드만 필터링
    target_hs = set(HS_TO_COMMODITY.keys())
    df = df[df["hs_code"].isin(target_hs)].copy()
    
    if df.empty:
        print(f"      ⚠️ 대상 HS코드 데이터 없음")
        return df
    
    # 숫자 변환 (공백+쉼표 포함 문자열 처리)
    for col in ["import_weight", "import_value"]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", "").str.strip(), 
            errors="coerce"
        ).fillna(0)
        
    # 날짜 변환 (YYYY.MM → YYYY-MM-01)
    df["date"] = pd.to_datetime(
        df["period"].str.replace(".", "-") + "-01",
        format="%Y-%m-%d",
        errors="coerce"
    )
    
    # 품목 ID 매핑
    df["commodity_id"] = df["hs_code"].map(HS_TO_COMMODITY)
    
    # 수입단가 산출: 금액(천달러) ÷ 중량(kg) × 1000 = $/톤
    # 중량이 0인 경우 단가 산출 불가 → NaN
    df["import_unit_price"] = None
    mask = df["import_weight"] > 0
    # 수입단가($/톤) = 금액(천달러) × 1,000,000 ÷ 중량(kg)
    # 천달러→달러: ×1000, kg→톤: ÷1000 → 합산 ×1,000,000
    df.loc[mask, "import_unit_price"] = (
        df.loc[mask, "import_value"] * 1_000_000 / df.loc[mask, "import_weight"]
    )
    # 필요한 컬럼만 선택
    result = df[[
        "date", "commodity_id", "hs_code",
        "import_weight", "import_value", "import_unit_price" 
    ]].copy()
    
    result = result.dropna(subset=["date"])
    
    print(f"      ✅ {len(result)}행 추출")
    return result


def parse_all_customs():
    """data/raw/customs/ 폴더의 모든 Excel 파일을 파싱하여 통합"""
    print("=" * 60)
    print(f"  관세청 수입단가 파싱")
    print("=" * 60)
    
    # Excel 파일 찾기
    excel_files = sorted(RAW_DIR.glob("customs_*.xlsx"))
    
    if not excel_files:
        # 다른 이름 패턴도 시도
        excel_files = sorted(RAW_DIR.glob("*.xlsx"))
    
    if not excel_files:
        print(f"  ❌ data/raw/customs/ 폴더에 Excel 파일이 없습니다.")
        print(f"     관세청에서 다운로드 후 해당 폴더에 저장해주세요.")
        return pd.DataFrame()
    
    print(f"  발견된 파일: {len(excel_files)}개")
    
    all_dfs = []
    for filepath in excel_files:
        df = parse_single_excel(filepath)
        if not df.empty:
            all_dfs.append(df)
    
    if not all_dfs:
        print(f"\n  ❌ 파싱된 데이터가 없습니다.")
        return pd.DataFrame()
    
    # 전체 합치기
    result = pd.concat(all_dfs, ignore_index=True)
    # 쇠고기(0201+0202) 합산: 같은 월의 중량·금액을 더한 뒤 단가 재계산
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
    
    # CSV 저장
    output_path = RAW_DIR / "customs_import_prices.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장 완료: {output_path}")
    
    # 요약
    print(f"\n  📋 수집 요약:")
    for cid in sorted(result["commodity_id"].unique()):
        sub = result[result["commodity_id"] == cid]
        valid = sub["import_unit_price"].dropna()
        
        if valid.empty:
            print(f"    {cid:<10} {len(sub):>4}개월  수입단가 산출 불가 (중량 0)")
            continue
        
        print(
            f"    {cid:<10} {len(sub):>4}개월  "
            f"{sub['date'].min().strftime('%Y-%m')}~{sub['date'].max().strftime('%Y-%m')}  "
            f"${valid.min():.0f}~${valid.max():.0f}/톤  "
            f"(최근 ${valid.iloc[-1]:.0f})"
        )
    
    # 중량 0인 월 경고
    zero_weight = result[result["import_weight"] == 0]
    if not zero_weight.empty:
        print(f"\n  ⚠️ 수입중량 0인 월: {len(zero_weight)}건 (수입단가 산출 불가)")
        for _, row in zero_weight.iterrows():
            print(f"     {row['date'].strftime('%Y-%m')} {row['commodity_id']} (HS {row['hs_code']})")
    
    return result


if __name__ == "__main__":
    parse_all_customs()
