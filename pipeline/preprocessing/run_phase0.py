"""Phase 0 전처리 통합 실행기. Step 1~5를 순차 실행한다."""

from pipeline.preprocessing.step1_convert_to_krw import convert_to_krw
from pipeline.preprocessing.step2_common_period import find_common_period
from pipeline.preprocessing.step3_missing_values import check_missing_values
from pipeline.preprocessing.step4_merge_datasets import merge_all_datasets
from pipeline.preprocessing.step5_product_config import generate_product_config


def run_phase0():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Phase 0. 전처리 통합 실행                              ║")
    print("╚══════════════════════════════════════════════════════════╝")

    results = {}

    print("\n\n" + "▶" * 25 + " Step 1: 국제가 원화 환산 " + "◀" * 25)
    try:
        df = convert_to_krw()
        results["step1"] = f"✅ {len(df)}행"
    except Exception as e:
        results["step1"] = f"❌ {e}"
        print(f"  ❌ Step 1 실패: {e}")

    print("\n\n" + "▶" * 25 + " Step 2: 공통 분석 기간 " + "◀" * 25)
    try:
        df = find_common_period()
        results["step2"] = f"✅ {len(df)}개 품목"
    except Exception as e:
        results["step2"] = f"❌ {e}"
        print(f"  ❌ Step 2 실패: {e}")

    print("\n\n" + "▶" * 25 + " Step 3: 결측치 처리 " + "◀" * 25)
    try:
        df = check_missing_values()
        results["step3"] = f"✅ {len(df)}개 시계열"
    except Exception as e:
        results["step3"] = f"❌ {e}"
        print(f"  ❌ Step 3 실패: {e}")

    print("\n\n" + "▶" * 25 + " Step 4: 통합 데이터셋 " + "◀" * 25)
    try:
        df = merge_all_datasets()
        results["step4"] = f"✅ {len(df)}행" if not df.empty else "❌ 빈 결과"
    except Exception as e:
        results["step4"] = f"❌ {e}"
        print(f"  ❌ Step 4 실패: {e}")

    print("\n\n" + "▶" * 25 + " Step 5: PRODUCT_CONFIG " + "◀" * 25)
    try:
        config = generate_product_config()
        results["step5"] = f"✅ {len(config)}개 품목"
    except Exception as e:
        results["step5"] = f"❌ {e}"
        print(f"  ❌ Step 5 실패: {e}")

    print("\n\n" + "=" * 60)
    print("  📋 Phase 0 전처리 결과 요약")
    print("=" * 60)
    for step, status in results.items():
        print(f"    {step}: {status}")

    print(f"\n  📂 출력 파일:")
    print(f"    data/processed/worldbank_prices_krw.csv     (원화 환산 국제가)")
    print(f"    data/processed/common_periods.csv           (공통 분석 기간)")
    print(f"    data/processed/missing_value_report.csv     (결측치 리포트)")
    print(f"    data/processed/merged/all_commodities.csv   (전체 통합 데이터셋)")
    print(f"    data/processed/merged/{{품목}}.csv            (품목별 개별 파일)")
    print(f"    data/processed/product_config.json          (품목별 분석 설정)")

    print(f"\n  다음 단계: Phase 1 (STL 계절 조정)")


if __name__ == "__main__":
    run_phase0()
