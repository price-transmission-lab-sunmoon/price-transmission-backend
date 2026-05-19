"""
World Bank Pink Sheet 데이터 수집기
==============================================
수집 대상: 밀, 옥수수, 대두 월별 국제가격 (USD)
실행 방법: python src/collectors/collect_worldbank.py

Pink Sheet Excel 파일을 다운로드하고 필요한 품목 컬럼만 추출합니다.
"""

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

# World Bank Pink Sheet 다운로드 URL (월별 가격 Excel)
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


def download_pink_sheet():
    """Pink Sheet Excel 파일 다운로드"""
    output_path = RAW_DIR / "CMO-Historical-Data-Monthly.xlsx"
    
    # 이미 다운로드된 파일이 있으면 재사용 (필요 시 삭제 후 재실행)
    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  ℹ️  이미 다운로드됨: {output_path.name} ({size_mb:.1f}MB)")
        print(f"     새로 받으려면 파일 삭제 후 재실행")
        return output_path
    
    print(f"  다운로드 중: {PINK_SHEET_URL}")
    print(f"  (파일 크기 ~5MB, 잠시 기다려주세요)")
    
    try:
        resp = requests.get(PINK_SHEET_URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ❌ 다운로드 실패: {e}")
        print(f"  수동 다운로드 후 {output_path}에 저장해주세요")
        print(f"  URL: https://www.worldbank.org/en/research/commodity-markets")
        return None
    
    with open(output_path, "wb") as f:
        f.write(resp.content)
    
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ 다운로드 완료: {output_path.name} ({size_mb:.1f}MB)")
    return output_path


def parse_pink_sheet(excel_path):
    """
    Pink Sheet Excel에서 밀/옥수수/대두 월별 가격 추출
    
    Pink Sheet 구조:
    - 시트명: "Monthly Prices"
    - 첫 몇 행은 메타데이터, 실제 데이터는 아래에 있음
    - 날짜 컬럼이 첫 번째, 이후 품목별 가격 컬럼
    """
    print(f"\n  Excel 파싱 중: {excel_path.name}")
    
    # 시트명 확인
    xls = pd.ExcelFile(excel_path)
    sheet_names = xls.sheet_names
    print(f"  시트 목록: {sheet_names}")
    
    # "Monthly Prices" 또는 유사한 시트 찾기
    target_sheet = None
    for name in sheet_names:
        if "monthly" in name.lower() and "price" in name.lower():
            target_sheet = name
            break
    
    if target_sheet is None:
        # 첫 번째 시트 사용
        target_sheet = sheet_names[0]
        print(f"  ⚠️ 'Monthly Prices' 시트 미발견, '{target_sheet}' 사용")
    else:
        print(f"  타겟 시트: {target_sheet}")
    
    # 헤더 행 찾기 (Pink Sheet는 상단에 메타데이터가 있음)
    # 먼저 전체 읽어서 구조 파악
    df_raw = pd.read_excel(excel_path, sheet_name=target_sheet, header=None, nrows=10)
    
    # Pink Sheet 고정 구조: 행4 = 품목명, 행5 = 단위, 행6~ = 데이터
    header_row = 4
    
    # 데이터 읽기
    df = pd.read_excel(excel_path, sheet_name=target_sheet, header=header_row)
    
    # 컬럼명 정리 (공백·줄바꿈 제거)
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    
    print(f"  전체 컬럼 수: {len(df.columns)}")
    print(f"  전체 행 수: {len(df)}")
    
    # 날짜 컬럼 찾기 (첫 번째 컬럼이 보통 날짜)
    date_col = df.columns[0]
    print(f"  날짜 컬럼: '{date_col}'")
    
    # 품목 매핑 파일에서 Pink Sheet 컬럼명 가져오기
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
        # 매핑 파일 없으면 기본값 사용
        column_map = {
            "wheat": "Wheat, US HRW",
            "maize": "Maize",
            "soybean": "Soybeans",
        }
    
    print(f"\n  찾을 품목 컬럼:")
    for cid, col_name in column_map.items():
        print(f"    {cid}: '{col_name}'")
    
    # 컬럼 매칭 (부분 매칭 지원)
    matched_columns = {}
    for cid, target_name in column_map.items():
        # 정확히 일치하는 컬럼 찾기
        exact = [c for c in df.columns if c == target_name]
        if exact:
            matched_columns[cid] = exact[0]
            continue
        
        # 부분 일치 (컬럼명에 target이 포함)
        partial = [c for c in df.columns if target_name.lower() in c.lower()]
        if partial:
            matched_columns[cid] = partial[0]
            continue
        
        # 키워드 기반 매칭
        keywords = target_name.lower().split(",")[0].split()  # 첫 단어
        keyword_match = [c for c in df.columns if all(kw in c.lower() for kw in keywords)]
        if keyword_match:
            matched_columns[cid] = keyword_match[0]
            continue
        
        print(f"    ⚠️ '{target_name}' 매칭 실패")
    
    if not matched_columns:
        print(f"\n  ❌ 품목 컬럼을 찾을 수 없습니다.")
        print(f"  사용 가능한 컬럼 목록 (처음 30개):")
        for c in df.columns[:30]:
            print(f"    - {c}")
        return pd.DataFrame()
    
    print(f"\n  매칭된 컬럼:")
    for cid, col in matched_columns.items():
        print(f"    ✅ {cid} → '{col}'")
    
    # 데이터 추출
    records = []
    for cid, col in matched_columns.items():
        subset = df[[date_col, col]].copy()
        subset.columns = ["date_raw", "value"]
        
        # 빈 값·비숫자 제거
        subset = subset.dropna(subset=["value"])
        subset = subset[subset["value"] != ".."]
        subset = subset[subset["value"] != "…"]
        
        # 날짜 파싱
        subset["date"] = pd.to_datetime(
            subset["date_raw"].astype(str).str.replace("M", "-"),
            format="%Y-%m",
            errors="coerce"
        )
        
        # 숫자 변환
        subset["value"] = pd.to_numeric(subset["value"], errors="coerce")
        subset = subset.dropna(subset=["value"])
        
        # 2000년 이후만
        subset = subset[subset["date"] >= "2000-01-01"]
        # 단위 변환: $/kg → $/mt (×1000)
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
    """World Bank Pink Sheet 전체 수집 프로세스"""
    print("=" * 60)
    print(f"  World Bank Pink Sheet 수집")
    print("=" * 60)
    
    # 다운로드
    excel_path = download_pink_sheet()
    if excel_path is None:
        return pd.DataFrame()
    
    # 파싱
    df = parse_pink_sheet(excel_path)
    
    if df.empty:
        print("\n  ❌ 추출된 데이터가 없습니다.")
        return df
    
    # CSV 저장
    output_path = RAW_DIR / "worldbank_prices.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장 완료: {output_path}")
    
    # 요약
    print(f"\n  📋 수집 요약:")
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
