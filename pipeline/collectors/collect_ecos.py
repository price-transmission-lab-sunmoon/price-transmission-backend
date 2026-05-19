"""
ECOS (한국은행 경제통계시스템) 데이터 수집기
==============================================
수집 대상: 생산자물가지수(PPI), 소비자물가지수(CPI) 품목별 월별 지수
실행 방법: python src/collectors/collect_ecos.py
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 설정
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# .env 로드
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

ECOS_API_KEY = os.getenv("ECOS_API_KEY", "")
if not ECOS_API_KEY:
    print("❌ .env에 ECOS_API_KEY가 없습니다.")
    sys.exit(1)

# 출력 경로
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ecos"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# ECOS API 호출 함수
# ============================================================
def fetch_ecos_data(stat_code, item_code, start_date, end_date, cycle="M"):
    """
    ECOS 통계검색 API 호출
    
    Parameters
    ----------
    stat_code : str   통계표코드 (예: "404Y014")
    item_code : str   품목코드 (예: "301131AA")
    start_date : str  시작일 (예: "200001")
    end_date : str    종료일 (예: "202512")
    cycle : str       주기 ("M"=월, "Q"=분기, "A"=연)
    
    Returns
    -------
    list[dict] : API 응답 row 목록
    """
    # ECOS API는 한 번에 최대 100,000건 반환 가능
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/"
        f"{ECOS_API_KEY}/json/kr/1/100000/"
        f"{stat_code}/{cycle}/{start_date}/{end_date}/{item_code}"
    )
    
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"    ❌ API 호출 실패: {e}")
        return []
    
    # 에러 체크
    if "RESULT" in data:
        msg = data["RESULT"].get("MESSAGE", "Unknown error")
        print(f"    ❌ API 에러: {msg}")
        return []
    
    rows = data.get("StatisticSearch", {}).get("row", [])
    return rows


def rows_to_dataframe(rows, commodity_id, data_type):
    """
    API 응답 row 목록을 DataFrame으로 변환
    
    Parameters
    ----------
    rows : list[dict]    API 응답
    commodity_id : str   품목 식별자 (예: "wheat")
    data_type : str      "ppi" 또는 "cpi"
    
    Returns
    -------
    pd.DataFrame : columns = [date, value, commodity_id, data_type, item_code, item_name, unit]
    """
    if not rows:
        return pd.DataFrame()
    
    records = []
    for r in rows:
        time_str = r.get("TIME", "")
        value_str = r.get("DATA_VALUE", "")
        
        # 빈 값 건너뛰기
        if not time_str or not value_str:
            continue
        
        # 월별 데이터만 처리 (YYYYMM 형식)
        if len(time_str) != 6:
            continue
        
        try:
            value = float(value_str)
        except ValueError:
            continue
        
        # YYYYMM → YYYY-MM-01 날짜로 변환
        date_str = f"{time_str[:4]}-{time_str[4:6]}-01"
        
        records.append({
            "date": date_str,
            "value": value,
            "commodity_id": commodity_id,
            "data_type": data_type,
            "item_code": r.get("ITEM_CODE1", ""),
            "item_name": r.get("ITEM_NAME1", ""),
            "unit": r.get("UNIT_NAME", ""),
            "stat_code": r.get("STAT_CODE", ""),
        })
    
    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    
    return df


# ============================================================
# 매핑 파일에서 수집 대상 읽기
# ============================================================
def load_collection_targets():
    """
    commodity_mapping.json에서 ECOS 수집 대상 목록 추출
    
    Returns
    -------
    list[dict] : [{commodity_id, data_type, stat_code, item_code, item_name}, ...]
    """
    mapping_path = PROJECT_ROOT / "config" / "commodity_mapping.json"
    
    if not mapping_path.exists():
        print(f"❌ 매핑 파일 없음: {mapping_path}")
        sys.exit(1)
    
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    
    targets = []
    
    for commodity in mapping.get("commodities", []):
        cid = commodity["commodity_id"]
        sources = commodity.get("sources", {})
        
        # PPI
        ppi = sources.get("ecos_ppi", {})
        if ppi.get("status") == "confirmed" and ppi.get("item_code"):
            targets.append({
                "commodity_id": cid,
                "data_type": "ppi",
                "stat_code": ppi["stat_code"],
                "item_code": ppi["item_code"],
                "item_name": ppi.get("item_name", ""),
            })
        
        # CPI (주 품목)
        cpi = sources.get("ecos_cpi", {})
        if cpi.get("status") == "confirmed" and cpi.get("item_code"):
            targets.append({
                "commodity_id": cid,
                "data_type": "cpi",
                "stat_code": cpi["stat_code"],
                "item_code": cpi["item_code"],
                "item_name": cpi.get("item_name", ""),
            })
        
        # CPI 대안 품목도 수집 (alternatives)
        for alt in cpi.get("alternatives", []):
            targets.append({
                "commodity_id": cid,
                "data_type": "cpi_alt",
                "stat_code": cpi["stat_code"],
                "item_code": alt["code"],
                "item_name": alt.get("name", ""),
            })
    
    return targets


# ============================================================
# 메인 수집 함수
# ============================================================
def collect_ecos(start_date="200001", end_date=None):
    """
    ECOS PPI/CPI 데이터 전체 수집
    
    Parameters
    ----------
    start_date : str  수집 시작 (YYYYMM), 기본값 2000년 1월
    end_date : str    수집 종료 (YYYYMM), 기본값 현재 월
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m")
    
    print("=" * 60)
    print(f"  ECOS 데이터 수집 (PPI / CPI)")
    print(f"  기간: {start_date} ~ {end_date}")
    print("=" * 60)
    
    targets = load_collection_targets()
    print(f"  수집 대상: {len(targets)}개 시계열")
    
    all_dfs = []
    
    for i, target in enumerate(targets):
        cid = target["commodity_id"]
        dtype = target["data_type"]
        stat_code = target["stat_code"]
        item_code = target["item_code"]
        item_name = target["item_name"]
        
        print(f"\n  [{i+1}/{len(targets)}] {cid} / {dtype} / {item_name} ({item_code})")
        
        # API 호출
        rows = fetch_ecos_data(stat_code, item_code, start_date, end_date)
        
        if not rows:
            print(f"    ⚠️ 데이터 없음")
            continue
        
        # DataFrame 변환
        df = rows_to_dataframe(rows, cid, dtype)
        
        if df.empty:
            print(f"    ⚠️ 유효한 데이터 없음")
            continue
        
        print(f"    ✅ {len(df)}개월 수집 완료 ({df['date'].min().strftime('%Y-%m')} ~ {df['date'].max().strftime('%Y-%m')})")
        all_dfs.append(df)
        
        # API 호출 간격 (과도한 요청 방지)
        time.sleep(0.3)
    
    if not all_dfs:
        print("\n  ❌ 수집된 데이터가 없습니다.")
        return pd.DataFrame()
    
    # 전체 합치기
    result = pd.concat(all_dfs, ignore_index=True)
    
    # CSV 저장
    output_path = RAW_DIR / "ecos_ppi_cpi.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장 완료: {output_path}")
    print(f"     전체 {len(result)}행, {result['commodity_id'].nunique()}개 품목")
    
    # 요약 출력
    print(f"\n  📋 수집 요약:")
    summary = result.groupby(["commodity_id", "data_type", "item_name"]).agg(
        months=("date", "count"),
        start=("date", "min"),
        end=("date", "max"),
    ).reset_index()
    
    for _, row in summary.iterrows():
        print(
            f"    {row['commodity_id']:<10} {row['data_type']:<8} {row['item_name']:<10} "
            f"{row['months']:>4}개월  {row['start'].strftime('%Y-%m')}~{row['end'].strftime('%Y-%m')}"
        )
    
    return result


# ============================================================
# 직접 실행
# ============================================================
if __name__ == "__main__":
    collect_ecos()
