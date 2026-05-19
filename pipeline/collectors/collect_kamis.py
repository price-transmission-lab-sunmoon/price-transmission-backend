"""
KAMIS 도매가 수집기 v3
==============================================
수집 대상: 쇠고기, 땅콩, 바나나, 오렌지 월별 도매가(중도매인 판매가격)
API: monthlySalesList

변경 이력:
  v1: periodProductList 사용 → 과거 데이터 조회 불가 문제
  v2: 재시도 로직 추가 → 근본 원인 미해결
  v3: monthlySalesList로 전환, 품목 코드 수정

핵심 발견사항:
  - periodProductList는 최근 데이터만 반환 (과거 조회 불가)
  - monthlySalesList는 p_yyyy 기준 과거 데이터 조회 가능
  - 품목 코드가 API마다 다름 (monthlySalesList 기준 코드 사용)
    바나나: 418 (dailyPrice에서는 416=단감)
    오렌지: 421 (dailyPrice에서는 420=파인애플)
    땅콩:   314 (dailyPrice에서는 313=들깨)
    쇠고기: 512 (dailyPrice에서는 511=데이터없음)

monthlySalesList 응답 구조:
  - price 배열 안에 productclscode별 블록
  - productclscode "02" = 중도매인 판매가격 (도매)
  - 각 블록에 item 배열 → 연도별 m1~m12 월별 가격
  - p_period=3 → 기준연도 포함 4개년 반환
  - caption으로 품목명/품종/등급/단위 확인 가능

실행: python src/collectors/collect_kamis.py
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CERT_KEY = os.getenv("KAMIS_CERT_KEY", "")
CERT_ID = os.getenv("KAMIS_CERT_ID", "")

if not CERT_KEY:
    print("❌ .env에 KAMIS_CERT_KEY가 없습니다.")
    sys.exit(1)

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "kamis"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://www.kamis.or.kr/service/price/xml.do"

# ============================================================
# monthlySalesList 기준 품목 코드 (검증 완료)
# ============================================================
KAMIS_TARGETS = [
    {
        "commodity_id": "groundnuts",
        "name_kr": "땅콩",
        "category_code": "300",
        "item_code": "314",       # monthlySalesList 기준
        "target_caption_keyword": "땅콩",
    },
    {
        "commodity_id": "banana",
        "name_kr": "바나나",
        "category_code": "400",
        "item_code": "418",       # monthlySalesList 기준
        "target_caption_keyword": "바나나",
    },
    {
        "commodity_id": "orange",
        "name_kr": "오렌지",
        "category_code": "400",
        "item_code": "421",       # monthlySalesList 기준
        "target_caption_keyword": "오렌지",
    },
]


# ============================================================
# API 호출
# ============================================================
def fetch_monthly(cat_code, item_code, yyyy, period="3", max_retries=3):
    """
    monthlySalesList API 호출

    Parameters
    ----------
    cat_code : str   부류코드
    item_code : str  품목코드 (monthlySalesList 기준)
    yyyy : str       기준 연도
    period : str     "1"=1년, "2"=2년, "3"=3년 (기준연도 포함 N+1개년 반환)

    Returns
    -------
    dict or None : API 응답 전체, 실패 시 None
    """
    params = {
        "action": "monthlySalesList",
        "p_cert_key": CERT_KEY,
        "p_cert_id": CERT_ID,
        "p_returntype": "json",
        "p_yyyy": yyyy,
        "p_period": period,
        "p_itemcategorycode": cat_code,
        "p_itemcode": item_code,
        "p_kindcode": "",
        "p_graderank": "",
        "p_countycode": "1101",
        "p_convert_kg_yn": "Y",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=45)
            return resp.json()
        except requests.exceptions.ConnectionError:
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"      ⚠️ 연결 실패 (시도 {attempt}/{max_retries}), {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(f"      ❌ 연결 실패 ({max_retries}회 모두 실패)")
                return None
        except Exception as e:
            print(f"      ❌ API 호출 실패: {e}")
            return None


def parse_price(price_str):
    """가격 문자열을 숫자로 변환 ("-", "," 등 처리)"""
    if not price_str or price_str == "-" or price_str == "0":
        return None
    try:
        return float(str(price_str).replace(",", "").strip())
    except ValueError:
        return None


# ============================================================
# 응답 파싱 — 중도매인 판매가격(도매) 블록에서 월별 데이터 추출
# ============================================================
def extract_wholesale_monthly(data, target_keyword):
    """
    monthlySalesList 응답에서 중도매인 판매가격(도매) 데이터 추출

    Parameters
    ----------
    data : dict          API 응답
    target_keyword : str 품목명 키워드 (caption 검증용)

    Returns
    -------
    list of dict : [{date, price}, ...]
    """
    prices_blocks = data.get("price", [])
    if not prices_blocks or not isinstance(prices_blocks, list):
        return []

    records = []

    for block in prices_blocks:
        if not isinstance(block, dict):
            continue

        cls_code = block.get("productclscode", "")
        caption = block.get("caption", "")

        # 중도매인 판매가격 = "02", 상품 등급 우선
        # caption에서 품목명 + "상품" 확인
        if cls_code != "02":
            continue
        if target_keyword not in caption:
            continue
        if "상품" not in caption:
            continue

        items = block.get("item", [])
        if not items or not isinstance(items, list):
            continue

        for year_data in items:
            if not isinstance(year_data, dict):
                continue

            yyyy = year_data.get("yyyy", "")
            if not yyyy:
                continue

            for month in range(1, 13):
                price = parse_price(year_data.get(f"m{month}", "-"))
                if price is None:
                    continue

                records.append({
                    "date": f"{yyyy}-{month:02d}-01",
                    "price": price,
                    "caption": caption,
                })

        # 상품 등급 블록을 찾았으면 중복 방지
        if records:
            break

    # 상품 등급이 없으면 중품이라도 사용
    if not records:
        for block in prices_blocks:
            if not isinstance(block, dict):
                continue
            cls_code = block.get("productclscode", "")
            caption = block.get("caption", "")
            if cls_code != "02" or target_keyword not in caption:
                continue

            items = block.get("item", [])
            if not items or not isinstance(items, list):
                continue

            for year_data in items:
                if not isinstance(year_data, dict):
                    continue
                yyyy = year_data.get("yyyy", "")
                if not yyyy:
                    continue
                for month in range(1, 13):
                    price = parse_price(year_data.get(f"m{month}", "-"))
                    if price is None:
                        continue
                    records.append({
                        "date": f"{yyyy}-{month:02d}-01",
                        "price": price,
                        "caption": caption,
                    })
            if records:
                break

    return records


# ============================================================
# 수집 함수
# ============================================================
def collect_kamis(start_year=2000, end_year=2026):
    """
    KAMIS 도매가(중도매인 판매가격) 전체 수집

    monthlySalesList는 p_period=3 → 기준연도 포함 4개년 반환
    → 4년 단위로 순회하여 전체 기간 커버
    """
    print("=" * 60)
    print(f"  KAMIS 도매가 수집 (monthlySalesList)")
    print(f"  기간: {start_year} ~ {end_year}")
    print("=" * 60)

    print(f"  수집 대상: {len(KAMIS_TARGETS)}개 품목")
    for t in KAMIS_TARGETS:
        print(f"    {t['commodity_id']:<12} {t['name_kr']} "
              f"(부류:{t['category_code']}, 품목:{t['item_code']})")

    all_records = []

    for target in KAMIS_TARGETS:
        cid = target["commodity_id"]
        name_kr = target["name_kr"]
        cat_code = target["category_code"]
        item_code = target["item_code"]
        keyword = target["target_caption_keyword"]

        print(f"\n  [{name_kr}] ({cid}) 수집 중...")

        item_records = []
        seen_dates = set()  # 중복 방지
        caption_logged = False

        # 4년 단위로 순회 (p_period=3 → 4개년 반환)
        # end_year부터 역순으로, 4년씩 건너뜀
        query_years = list(range(end_year, start_year - 1, -4))
        # start_year 근처에서 누락 방지
        if query_years[-1] > start_year:
            query_years.append(start_year)

        for yyyy in query_years:
            data = fetch_monthly(cat_code, item_code, str(yyyy), period="3")
            if data is None:
                print(f"    {yyyy}: ❌ 호출 실패")
                continue

            records = extract_wholesale_monthly(data, keyword)

            if not records:
                print(f"    {yyyy}: 데이터 없음")
                continue

            # caption 로그 (한 번만)
            if not caption_logged and records:
                print(f"    caption: {records[0]['caption']}")
                caption_logged = True

            # 중복 제거 후 추가
            new_count = 0
            for r in records:
                if r["date"] not in seen_dates:
                    seen_dates.add(r["date"])
                    item_records.append({
                        "date": r["date"],
                        "commodity_id": cid,
                        "item_name": name_kr,
                        "price": r["price"],
                        "unit": "원/kg",
                    })
                    new_count += 1

            years_in_batch = sorted(set(r["date"][:4] for r in records))
            print(f"    기준연도 {yyyy}: {new_count}건 추가 "
                  f"(연도: {', '.join(years_in_batch)})")

            time.sleep(0.3)

        # 품목 요약
        if item_records:
            prices = [r["price"] for r in item_records]
            dates = sorted(r["date"] for r in item_records)
            print(f"    ─ 소계: {len(item_records)}개월, "
                  f"{dates[0][:7]}~{dates[-1][:7]}, "
                  f"{min(prices):,.0f}~{max(prices):,.0f} 원/kg")
        else:
            print(f"    ─ 소계: 0건")

        all_records.extend(item_records)

    if not all_records:
        print("\n  ❌ 수집된 데이터가 없습니다.")
        return pd.DataFrame()

    # DataFrame 변환
    df = pd.DataFrame(all_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["commodity_id", "date"]).reset_index(drop=True)

    # 월별 데이터 저장 (monthlySalesList는 이미 월별)
    monthly_path = RAW_DIR / "kamis_wholesale_monthly.csv"
    df.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 월별 저장: {monthly_path} ({len(df)}건)")

    # 요약
    print(f"\n  📋 수집 요약:")
    for cid in sorted(df["commodity_id"].unique()):
        sub = df[df["commodity_id"] == cid]
        print(
            f"    {cid:<12} {sub['item_name'].iloc[0]:<8} "
            f"{len(sub):>4}개월  "
            f"{sub['date'].min().strftime('%Y-%m')}~{sub['date'].max().strftime('%Y-%m')}  "
            f"{sub['price'].min():,.0f}~{sub['price'].max():,.0f} 원/kg"
        )

    return df


if __name__ == "__main__":
    collect_kamis()