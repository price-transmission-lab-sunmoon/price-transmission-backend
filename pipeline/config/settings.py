"""
프로젝트 공통 설정
- API 키는 .env 파일에서 로드
- 파이프라인 파라미터는 신청서 기준값 사전 고정
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# === 프로젝트 경로 ===
PROJECT_ROOT = Path(__file__).parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_OUTPUT = PROJECT_ROOT / "data" / "output"

# === API 키 ===
ECOS_API_KEY = os.getenv("ECOS_API_KEY", "")
EXIM_API_KEY = os.getenv("EXIM_API_KEY", "")
KAMIS_CERT_KEY = os.getenv("KAMIS_CERT_KEY", "")
KAMIS_CERT_ID = os.getenv("KAMIS_CERT_ID", "")

# === 분석 기간 (데이터 가용성 확인 후 확정) ===
ANALYSIS_START = "2000-01"   # 잠정
ANALYSIS_END = "2025-12"     # 잠정

# === 파이프라인 파라미터 (신청서 기준값) ===
RANDOM_STATE = 42

# Phase 1: STL
STL_PERIOD = 12              # 월별 데이터 계절 주기
STL_ROBUST = True            # 이상치 강건 STL

# Phase 2: 정상성 검정
ADF_SIGNIFICANCE = 0.05
KPSS_SIGNIFICANCE = 0.05

# Phase 3: Johansen 공적분 검정
JOHANSEN_DET_ORDER = 0       # 결정론적 추세 없음

# Phase 4: VAR/VECM
LAG_SEARCH_RANGE = range(1, 5)  # 1~4

# Phase 6: 구조 변화
MIN_SUBPERIOD_OBS = 60       # 하위 기간 최소 관측치

# Phase 7: 이상 탐지
ROLLING_WINDOW = 48          # 기본 롤링 윈도우 크기 (개월)
ROLLING_WINDOW_ROBUSTNESS = [36, 48, 60]  # 로버스트니스 체크용
ZSCORE_WARNING = 2.0         # Z-score 주의 임계값
ZSCORE_ALERT = 2.5           # Z-score 경보 임계값
IQR_MULTIPLIER = 1.5         # Tukey 표준
STABILITY_THRESHOLD = 0.03   # 국제가 안정 구간 (±3%)
PATTERN3_N_VALUES = [2, 3, 6]  # N값 3단계

# Phase 7-ML: ML 파라미터
IF_N_ESTIMATORS = 100
CONTAMINATION_RANGE = [0.05, 0.10, 0.15]
LOF_N_NEIGHBORS_RANGE = range(5, 21)
SVM_KERNEL = "rbf"

# Phase 0: 결측치 처리
MAX_MISSING_RATE = 0.10      # 10% 이상 결측 품목 제외
MAX_CONSECUTIVE_MISSING = 3  # 연속 결측 3개월 이상 플래그
