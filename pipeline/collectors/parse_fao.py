"""FAO Food Price Index CSV 파일을 파싱해 품목군별 월별 지수를 추출하는 파서 (2014-2016=100)."""

import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "fao"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def parse_fao_ffpi():
    """FAO FFPI CSV 파싱. 헤더는 3행째(header=2)."""
    print("=" * 60)
    print("  FAO Food Price Index 파싱")
    print("=" * 60)

    csv_path = RAW_DIR / "food_price_indices_data.csv"

    if not csv_path.exists():
        print(f"  파일 없음: {csv_path}")
        print("  https://www.fao.org/worldfoodsituation/foodpricesindex/en/ 에서 다운로드 필요")
        return pd.DataFrame()

    df = pd.read_csv(csv_path, header=2)
    df.columns = [str(c).strip() for c in df.columns]

    print(f"  컬럼: {list(df.columns)}, 전체 행: {len(df)}")

    date_col = df.columns[0]

    df = df.dropna(subset=[date_col])
    df = df[df[date_col].astype(str).str.strip() != ""]

    # Jan-90 형식 파싱, 실패 시 다른 형식 재시도
    df["date"] = pd.to_datetime(df[date_col], format="%b-%y", errors="coerce")

    mask_null = df["date"].isna()
    if mask_null.any():
        df.loc[mask_null, "date"] = pd.to_datetime(
            df.loc[mask_null, date_col], errors="coerce"
        )

    df = df.dropna(subset=["date"])
    df = df[df["date"] >= "2000-01-01"].copy()

    column_map = {
        "Food Price Index": "food_price_index",
        "Meat": "meat",
        "Dairy": "dairy",
        "Cereals": "cereals",
        "Oils": "oils",
        "Sugar": "sugar",
    }

    found_cols = {}
    for orig, new in column_map.items():
        matches = [c for c in df.columns if orig.lower() in c.lower()]
        if matches:
            found_cols[matches[0]] = new

    print("\n  매칭된 품목군:")
    for orig, new in found_cols.items():
        print(f"    '{orig}' 컬럼을 {new}으로 매칭")

    for col in found_cols.keys():
        df[col] = pd.to_numeric(df[col], errors="coerce")

    result = df[["date"] + list(found_cols.keys())].copy()
    result = result.rename(columns=found_cols)
    result = result.sort_values("date").reset_index(drop=True)

    output_path = RAW_DIR / "fao_ffpi_monthly.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  저장 완료: {output_path}")

    print("\n  수집 요약:")
    print(f"     기간: {result['date'].min().strftime('%Y-%m')} ~ {result['date'].max().strftime('%Y-%m')}")
    print(f"     월수: {len(result)}개월")
    for col in found_cols.values():
        missing = result[col].isna().sum()
        last_val = result[col].dropna().iloc[-1] if not result[col].dropna().empty else "N/A"
        print(f"       {col:<20} 결측: {missing}건  최근: {last_val}")

    return result


if __name__ == "__main__":
    parse_fao_ffpi()
