"""파이프라인 공통 설정. API 키는 .env에서 로드."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_OUTPUT = PROJECT_ROOT / "data" / "output"

ECOS_API_KEY = os.getenv("ECOS_API_KEY", "")
EXIM_API_KEY = os.getenv("EXIM_API_KEY", "")
KAMIS_CERT_KEY = os.getenv("KAMIS_CERT_KEY", "")
KAMIS_CERT_ID = os.getenv("KAMIS_CERT_ID", "")

ANALYSIS_START = "2000-01"
ANALYSIS_END = "2025-12"

RANDOM_STATE = 42

# STL 분해
STL_PERIOD = 12
STL_ROBUST = True

# 정상성 검정
ADF_SIGNIFICANCE = 0.05
KPSS_SIGNIFICANCE = 0.05

# Johansen 공적분 검정
JOHANSEN_DET_ORDER = 0

# VAR/VECM
LAG_SEARCH_RANGE = range(1, 5)

# 구조 변화
MIN_SUBPERIOD_OBS = 60

# 이상 탐지
ROLLING_WINDOW = 48
ROLLING_WINDOW_ROBUSTNESS = [36, 48, 60]
ZSCORE_WARNING = 2.0
ZSCORE_ALERT = 2.5
IQR_MULTIPLIER = 1.5         # Tukey 표준
STABILITY_THRESHOLD = 0.03
PATTERN3_N_VALUES = [2, 3, 6]

# Isolation Forest / LOF / SVM
IF_N_ESTIMATORS = 100
CONTAMINATION_RANGE = [0.05, 0.10, 0.15]
LOF_N_NEIGHBORS_RANGE = range(5, 21)
SVM_KERNEL = "rbf"

# 결측치 처리 임계값
MAX_MISSING_RATE = 0.10
MAX_CONSECUTIVE_MISSING = 3
