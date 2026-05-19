"""
한국수출입은행 환율 데이터 수집기
==============================================
수집 대상: USD/KRW 일별 매매기준율 → 월평균 집계
실행 방법: python src/collectors/collect_exchange_rate.py
"""

import os
import sys
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
# 경고 비활성화
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 프로젝트 루트 설정
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

EXIM_API_KEY = os.getenv("EXIM_API_KEY", "")
if not EXIM_API_KEY:
    print("❌ .env에 EXIM_API_KEY가 없습니다.")
    sys.exit(1)

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "exchange_rate"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"


# ============================================================
# API 호출
# ============================================================
def fetch_daily_rate(search_date):
    """
    특정 날짜의 환율 조회
    
    Parameters
    ----------
    search_date : date  조회 날짜
    
    Returns
    -------
    dict or None : USD 환율 데이터 (deal_bas_r = 매매기준율)
    """
    date_str = search_date.strftime("%Y%m%d")
    params = {
        "authkey": EXIM_API_KEY,
        "searchdate": date_str,
        "data": "AP01",
    }
    
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15, verify=False)
        data = resp.json()
    except Exception:
        return None
    
    if not data or isinstance(data, dict):
        return None
    
    for d in data:
        if d.get("cur_unit") == "USD":
            return {
                "date": search_date,
                "deal_bas_r": d.get("deal_bas_r", ""),
                "ttb": d.get("ttb", ""),
                "tts": d.get("tts", ""),
            }
    
    return None

def fetch_daily_rate_with_retry(target_date, max_retry=3):
    """
    target_date 조회 실패 시 ±1~3일 범위에서 재시도 하는 함수
    """
    # 원래 날짜 먼저 시도
    result = fetch_daily_rate(target_date)
    if result:
        return result
    
    # 실패 시 앞뒤 날짜로 재시도
    for offset in range(1, max_retry + 1):
        for delta in [-offset, offset]:
            retry_date = target_date + timedelta(days=delta)
            if retry_date.weekday() >= 5:  # 주말 건너뛰기
                continue
            result = fetch_daily_rate(retry_date)
            if result:
                return result
            time.sleep(0.5)
    
    return None


def collect_exchange_rate(start_year=2000, end_date=None):
    """
    일별 USD/KRW 환율 수집 + 월평균 산출
    
    Parameters
    ----------
    start_year : int   수집 시작 연도
    end_date : date    수집 종료일 (기본값: 오늘)
    """
    if end_date is None:
        end_date = date.today()
    
    start_date = date(start_year, 1, 1)
    
    print("=" * 60)
    print(f"  환율 데이터 수집 (USD/KRW)")
    print(f"  기간: {start_date} ~ {end_date}")
    print("=" * 60)
    
    # --- 전략: 월의 마지막 영업일 기준으로 수집 ---
    # 매일 수집하면 API 호출이 너무 많으므로 (약 9,000일),
    # 각 월의 영업일 몇 개를 샘플링하여 월평균 산출
    # 더 정확한 방법: 월 단위로 15일, 말일 등 복수 조회
    
    daily_records = []
    current = start_date
    
    # 월 단위로 순회하며 해당 월의 여러 날짜를 조회
    months_processed = 0
    total_months = (end_date.year - start_year) * 12 + end_date.month
    
    while current <= end_date:
        year, month = current.year, current.month
        months_processed += 1
        
        if months_processed % 24 == 0:
            print(f"  진행 중: {year}-{month:02d} ({months_processed}/{total_months})")
        
        # API 호출 리미트 때문에 월 2회로 변경 했었다가 월 5회로 확대, 2회로 나누어 진행(04.06기준)
        sample_days = [1, 7, 13, 19, 25]
        
        for day in sample_days:
            try:
                query_date = date(year, month, min(day, 28))
            except ValueError:
                continue
            
            if query_date > end_date:
                break
            
            # 주말이면 직전 금요일로
            while query_date.weekday() >= 5:
                query_date -= timedelta(days=1)
            
            result = fetch_daily_rate_with_retry(query_date)
            if result:
                daily_records.append(result)
            
            time.sleep(1.0)  # API 부하 방지
        
        # 다음 달로
        if month == 12:
            current = date(year + 1, 1, 1)
        else:
            current = date(year, month + 1, 1)
    
    if not daily_records:
        print("  ❌ 수집된 데이터가 없습니다.")
        return pd.DataFrame()
    
    # DataFrame 변환
    df = pd.DataFrame(daily_records)
    df["date"] = pd.to_datetime(df["date"])
    
    # 매매기준율 숫자 변환 (쉼표 제거)
    for col in ["deal_bas_r", "ttb", "tts"]:
        df[col] = df[col].astype(str).str.replace(",", "").astype(float)
    
    # 일별 원본 저장
    daily_path = RAW_DIR / "exchange_rate_daily.csv"
    if daily_path.exists():
        existing = pd.read_csv(daily_path, parse_dates=["date"])
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    df.to_csv(daily_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 일별 원본 저장: {daily_path} ({len(df)}건)")
    
    # 월평균 집계
    df["year_month"] = df["date"].dt.to_period("M")
    monthly = df.groupby("year_month").agg(
        exchange_rate_avg=("deal_bas_r", "mean"),
        exchange_rate_min=("deal_bas_r", "min"),
        exchange_rate_max=("deal_bas_r", "max"),
        sample_count=("deal_bas_r", "count"),
    ).reset_index()
    
    # period를 datetime으로 변환
    monthly["date"] = monthly["year_month"].dt.to_timestamp()
    monthly = monthly.drop(columns=["year_month"])
    monthly = monthly[["date", "exchange_rate_avg", "exchange_rate_min", 
                        "exchange_rate_max", "sample_count"]]
    monthly = monthly.sort_values("date").reset_index(drop=True)
    
    # 월평균 저장
    monthly_path = RAW_DIR / "exchange_rate_monthly.csv"
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    print(f"  💾 월평균 저장: {monthly_path} ({len(monthly)}개월)")
    
    # 요약
    print(f"\n  📋 수집 요약:")
    print(f"     기간: {monthly['date'].min().strftime('%Y-%m')} ~ {monthly['date'].max().strftime('%Y-%m')}")
    print(f"     월수: {len(monthly)}개월")
    print(f"     최근 환율: {monthly.iloc[-1]['exchange_rate_avg']:.1f} 원/달러")
    
    return monthly


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=None)
    args = parser.parse_args()
    
    end = date(args.end_year, 12, 31) if args.end_year else None
    collect_exchange_rate(start_year=args.start, end_date=end)