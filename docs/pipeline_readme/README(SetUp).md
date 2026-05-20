# 개발 환경 셋업 가이드

> **대상**: price-transmission 팀원 전원  
> **소요 시간**: 약 10분  
> **전제 조건**: Python 3.10 이상, Git 설치 완료

---

## 1. 레포 클론

```bash
git clone https://github.com/price-transmission-lab-sunmoon/price-transmission.git
cd price-transmission
```

---

## 2. 가상환경 생성 + 패키지 설치

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Mac / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 설치 확인

```bash
python -c "import pandas; import statsmodels; import scipy; import ruptures; import sklearn; import requests; print('모든 패키지 정상!')"
```

`모든 패키지 정상!`이 출력되면 완료.

---

## 3. .env 파일 생성 (API 키 입력)

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

`.env` 파일을 열어서 실제 API 키를 입력합니다.

```
ECOS_API_KEY=
EXIM_API_KEY=
KAMIS_CERT_KEY=
KAMIS_CERT_ID=
```

> **주의**: `.env` 파일은 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.  
> API 키는 팀 메신저로 별도 공유합니다. 커밋하지 마세요.

---

## 4. 작업 시작 전 매번 할 일

터미널을 새로 열 때마다 가상환경을 활성화해야 합니다.

```bash
# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

프롬프트 앞에 `(.venv)`가 보이면 활성화된 상태입니다.

---

## 트러블슈팅

### numpy 설치 에러 (Python 3.13)

`numpy<2.0` 버전이 Python 3.13에서 빌드 실패하는 경우:

```bash
pip install numpy>=1.26 --force-reinstall
pip install -r requirements.txt
```

### pip 업그레이드 실패 (Windows)

```bash
python -m pip install --upgrade pip
```

### 가상환경 삭제 후 재생성

문제가 해결되지 않으면 가상환경을 지우고 처음부터 다시:

```bash
# Windows
rmdir /s /q .venv

# Mac / Linux
rm -rf .venv
```

이후 2번 과정을 처음부터 반복합니다.

---

## 프로젝트 폴더 구조

```
price-transmission/
├── data/
│   ├── raw/              ← 원본 데이터 (소스별 하위 폴더)
│   │   ├── worldbank/
│   │   ├── fao/
│   │   ├── customs/
│   │   ├── exchange_rate/
│   │   ├── ecos/
│   │   └── kamis/
│   ├── processed/        ← 전처리 완료 데이터
│   └── output/           ← 분석 결과
├── src/
│   ├── collectors/       ← 데이터 수집 모듈
│   ├── preprocessing/    ← Phase 0~1
│   ├── analysis/         ← Phase 2~7
│   ├── ml/               ← Phase 7-ML
│   └── utils/            ← 공통 유틸
├── config/
│   └── settings.py       ← 파이프라인 파라미터 (신청서 기준값)
├── notebooks/            ← Jupyter 탐색 분석
├── docs/                 ← 문서
├── tests/                ← 테스트 용 파일 위치. 각각의 테스트 파일 최상단에 간단한 요약 적기
├── .env                  ← API 키 (git 추적 안 됨)
├── .env.example          ← API 키 템플릿
├── .gitignore
├── requirements.txt
└── README(SetUp).md      ← 이 파일
```

---

## 핵심 라이브러리 버전

| 패키지        | 버전   | 용도                                 |
| ------------- | ------ | ------------------------------------ |
| pandas        | ≥ 2.0  | 데이터 처리                          |
| numpy         | ≥ 1.26 | 수치 연산                            |
| statsmodels   | ≥ 0.14 | VAR/VECM, ADF/KPSS, IRF, Johansen    |
| scipy         | ≥ 1.11 | 통계 검정, Wald 검정                 |
| ruptures      | ≥ 1.1  | Bai-Perron 구조 변화 탐지            |
| scikit-learn  | ≥ 1.4  | Isolation Forest, LOF, One-Class SVM |
| matplotlib    | ≥ 3.7  | 시각화                               |
| seaborn       | ≥ 0.13 | 분포·히트맵 시각화                   |
| requests      | ≥ 2.31 | API 호출                             |
| python-dotenv | ≥ 1.0  | .env 파일 로드                       |
| openpyxl      | ≥ 3.1  | Excel 파일 읽기                      |

---

## API 키 발급처

| API             | 발급 URL                                                       | 비고                           |
| --------------- | -------------------------------------------------------------- | ------------------------------ |
| ECOS (한국은행) | https://ecos.bok.or.kr → Open API → 인증키 신청                | 회원가입 시 자동 발급          |
| 한국수출입은행  | https://www.koreaexim.go.kr/ir/HPHKIR020M01?apino=2&viewtype=C | 본인인증 후 즉시 발급          |
| KAMIS           | https://www.kamis.or.kr → Open-API 사용신청                    | cert_key + cert_id 두 개 필요  |
| 관세청          | https://unipass.customs.go.kr                                  | API 키 불필요 (Excel 다운로드) |
