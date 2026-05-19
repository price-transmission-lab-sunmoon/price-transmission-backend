"""
FAO Food Price Index 파서
==============================================
수집 대상: 5개 품목군 월별 지수 (2014-2016=100)
  - Food Price Index (종합)
  - Meat (육류)
  - Dairy (유제품)
  - Cereals (곡물)
  - Oils (식물성유)
  - Sugar (설탕)
실행 방법: python src/collectors/parse_fao.py
"""

import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "fao"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def parse_fao_ffpi():
    """FAO FFPI CSV 파싱"""
    print("=" * 60)
    print("  FAO Food Price Index 파싱")
    print("=" * 60)

    # 파일 찾기
    csv_path = RAW_DIR / "food_price_indices_data.csv"

    if not csv_path.exists():
        print(f"  ❌ 파일 없음: {csv_path}")
        print(f"     https://www.fao.org/worldfoodsituation/foodpricesindex/en/ 에서 다운로드 후 저장")
        return pd.DataFrame()

    # CSV 읽기 (헤더가 3행째, 0-indexed로 2)
    df = pd.read_csv(csv_path, header=2)
    df.columns = [str(c).strip() for c in df.columns]

    print(f"  컬럼: {list(df.columns)}")
    print(f"  전체 행: {len(df)}")

    # 날짜 컬럼 찾기
    date_col = df.columns[0]
    print(f"  날짜 컬럼: '{date_col}'")

    # 빈 행 제거
    df = df.dropna(subset=[date_col])
    df = df[df[date_col].astype(str).str.strip() != ""]

    # 날짜 파싱 (Jan-90 형식)
    df["date"] = pd.to_datetime(df[date_col], format="%b-%y", errors="coerce")

    # 파싱 안 되는 경우 다른 형식 시도
    mask_null = df["date"].isna()
    if mask_null.any():
        df.loc[mask_null, "date"] = pd.to_datetime(
            df.loc[mask_null, date_col], errors="coerce"
        )

    df = df.dropna(subset=["date"])

    # 2000년 이후만
    df = df[df["date"] >= "2000-01-01"].copy()

    # 품목군 컬럼 매핑
    column_map = {
        "Food Price Index": "food_price_index",
        "Meat": "meat",
        "Dairy": "dairy",
        "Cereals": "cereals",
        "Oils": "oils",
        "Sugar": "sugar",
    }

    # 실제 존재하는 컬럼만 매핑
    found_cols = {}
    for orig, new in column_map.items():
        matches = [c for c in df.columns if orig.lower() in c.lower()]
        if matches:
            found_cols[matches[0]] = new

    print(f"\n  매칭된 품목군:")
    for orig, new in found_cols.items():
        print(f"    ✅ '{orig}' → {new}")

    # 숫자 변환
    for col in found_cols.keys():
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 필요한 컬럼만 추출
    result = df[["date"] + list(found_cols.keys())].copy()
    result = result.rename(columns=found_cols)
    result = result.sort_values("date").reset_index(drop=True)

    # 저장
    output_path = RAW_DIR / "fao_ffpi_monthly.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 저장 완료: {output_path}")

    # 요약
    print(f"\n  📋 수집 요약:")
    print(f"     기간: {result['date'].min().strftime('%Y-%m')} ~ {result['date'].max().strftime('%Y-%m')}")
    print(f"     월수: {len(result)}개월")
    print(f"     결측치:")
    for col in found_cols.values():
        missing = result[col].isna().sum()
        last_val = result[col].dropna().iloc[-1] if not result[col].dropna().empty else "N/A"
        print(f"       {col:<20} 결측: {missing}건  최근: {last_val}")

    # 품목 매핑 참고 출력
    print(f"\n  📌 우리 품목과의 교차검증 매핑:")
    print(f"     밀·옥수수        → Cereals (곡물 지수)")
    print(f"     대두·팜유        → Oils (식물성유 지수)")
    print(f"     설탕            → Sugar (설탕 지수)")
    print(f"     쇠고기           → Meat (육류 지수)")
    print(f"     커피·땅콩·바나나·오렌지 → 직접 매핑 없음 (종합 지수로 교차검증)")

    return result


if __name__ == "__main__":
    parse_fao_ffpi()
