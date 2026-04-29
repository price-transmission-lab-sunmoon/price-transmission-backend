# Frame 명세서 — frontend

**문서 유형**: Frame 명세서 (v3)
**브랜치명**: `frame/frontend`
**담당자**: 하대수 (sprint_plan §3.2 기준)
**작성 기준 문서**:
- `doc1_technical_pipeline_v9.md`
- `doc3_research_proposal_v11.md`
- `web_plan_v6.md`
- `pipeline_output_spec_v5.md`
- `db_schema_v3.md`
- `api_spec_v4.md`
- `exception_spec_v2.md`

**작성일**: 2026-04-26
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-04-24): 최초 작성.
- v2 (2026-04-24): 자체 검증 결과 반영 — `pipeline_output_spec` 참조 버전 정정, `VITE_USE_MOCK` 필수 여부 정정, `.eslintignore`/`.prettierignore` 추가.
- v3 (2026-04-26): 참조 문서 일괄 갱신 (db_schema v3, api_spec v4, exception_spec v2, doc1 v9, doc3 v11). 백엔드 Frame 명세 v2 양식을 참고하여 명확성 보강 — §1 smoke test 행 추가, §3 "출처" 열로 변경 + 본 Frame 단독 정의 명시, §4 예외 코드 매핑, §6.3 Literal 타입 사용 원칙 신설, §6.4 에러 응답 envelope 스키마 신설, §6.5 날짜·시각 역직렬화 정책 신설, §7.4 smoke test 3건 신설, §8 라우터 prefix 정책·도구 설정·CORS 처리 보강. §8.10 절대 금지 사항을 표 형식으로 재구성. §9 PM 승인 항목 9개로 확장.

---

## 1. 완료 기준

이 Frame 명세의 완료는 아래 조건을 모두 충족한 시점으로 한다.

| 항목 | 조건 |
|------|------|
| 로컬 실행 | 더미 데이터 기준 `npm run dev` 오류 없이 실행 성공 |
| 진입점 응답 | 브라우저 접속 후 빈 레이아웃 렌더링 확인 (헤더·필터 바·메인 영역·우측 패널 자리 표시자) |
| API 연결 검증 | `VITE_USE_MOCK=true` 상태에서 `App.tsx` 마운트 시 `/api/v1/commodities` 모의 요청 1회 성공, 콘솔 응답 본문에 `commodity_id`, `cluster`, `route_type` 키 존재 |
| 타입 일치 | `db_schema_v3 ↔ api_spec_v4 ↔ src/types/` 3방향 필드명 + Literal 값 일치 (불일치 0건) |
| 문서 첨부 | `docs/` 폴더에 명세 8종 + CLAUDE.md 사본 존재 |
| Smoke test | §7.4 정의 3건 모두 통과 |

> 템플릿 §1 "연결 확인" 행은 백엔드 전용(DB·Redis ping)이므로 프론트엔드에서는 "API 연결 검증"으로 대체한다.

---

## 2. 디렉토리 구조

> 모든 폴더·파일은 이 Frame PR 시점에 실제로 생성하여 커밋한다. 빈 폴더는 `.gitkeep`을 둔다.

```
frontend/
├── public/
│   └── favicon.svg                  ← 파비콘
├── src/
│   ├── api/
│   │   ├── client.ts                ← Axios 인스턴스 (baseURL·타임아웃·에러 인터셉터·MOCK 분기)
│   │   ├── endpoints.ts             ← api_spec_v4 엔드포인트 18종 경로 상수
│   │   └── error.ts                 ← API 에러 envelope 파서 + ApiError 클래스
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx         ← 전체 레이아웃 래퍼
│   │   │   ├── Header.tsx           ← 상단 바 자리 표시자 (web_plan_v6 §3.3)
│   │   │   ├── FilterBar.tsx        ← 필터 바 자리 표시자 (web_plan_v6 §3.4)
│   │   │   └── Panel.tsx            ← 우측 분석 수치 패널 자리 표시자 (web_plan_v6 §6)
│   │   └── charts/
│   │       └── .gitkeep             ← 후속 feat 브랜치에서 D3.js 컴포넌트 추가 (§8.6)
│   ├── stores/
│   │   └── useAppStore.ts           ← Zustand 전역 스토어 (타입 선언과 빈 기본값)
│   ├── types/
│   │   ├── commodity.ts             ← 품목·구간 타입 (api_spec_v4 /commodities 응답 1:1)
│   │   ├── anomaly.ts               ← 이상 탐지 타입 (api_spec_v4 /anomalies/* 응답 1:1, ml_projections 포함)
│   │   ├── timeseries.ts            ← 시계열 공통 envelope 타입 (api_spec_v4 §시계열 공통 envelope)
│   │   ├── event.ts                 ← 외부 이벤트 타입 (api_spec_v4 /events 응답 1:1)
│   │   ├── meta.ts                  ← /meta/config·/freshness 응답 타입
│   │   ├── error.ts                 ← API 에러 envelope 타입 (§6.4)
│   │   ├── literals.ts              ← Literal 값 상수·유니온 타입 (§6.3)
│   │   └── index.ts                 ← barrel re-export
│   ├── fixtures/
│   │   ├── commodities.json         ← /commodities 목업 응답 (db_schema_v3 §commodities 초기 데이터 10행)
│   │   ├── segments.json            ← /segments 목업 응답 (db_schema_v3 §segments 초기 데이터 5행)
│   │   ├── events.json              ← /events 목업 응답 (db_schema_v3 §external_events 초기 데이터 5행)
│   │   └── freshness.json           ← /freshness 목업 응답 (§8.1 고정값)
│   ├── services/
│   │   └── .gitkeep                 ← 후속 feat 브랜치에서 데이터 변환·집계 로직 추가 (§8.7)
│   ├── pages/
│   │   └── MainPage.tsx             ← 메인 페이지 (뷰 탭 자리 표시자)
│   ├── router/
│   │   └── index.tsx                ← React Router v6 라우터 (메인 1개 경로)
│   ├── App.tsx                      ← 최상위 컴포넌트 (QueryClientProvider + RouterProvider)
│   ├── main.tsx                     ← Vite 진입점
│   ├── index.css                    ← Tailwind import
│   └── vite-env.d.ts                ← Vite 환경 변수 타입 선언
├── tests/
│   ├── setup.ts                     ← Vitest 환경 설정 (@testing-library/jest-dom 등록)
│   └── frame_smoke.test.ts          ← §7.4 smoke test 3건
├── docs/                            ← 명세 8종 + CLAUDE.md 사본
│   ├── doc1_technical_pipeline_v9.md
│   ├── doc3_research_proposal_v11.md
│   ├── web_plan_v6.md
│   ├── pipeline_output_spec_v5.md
│   ├── db_schema_v3.md
│   ├── api_spec_v4.md
│   ├── exception_spec_v2.md
│   ├── sprint_plan.md
│   └── CLAUDE.md
├── .env.example                     ← 환경 변수 예시
├── .gitignore                       ← node_modules, dist, .env 제외
├── .eslintrc.cjs                    ← ESLint 설정
├── .eslintignore                    ← node_modules, dist
├── .prettierrc                      ← Prettier 설정
├── .prettierignore                  ← node_modules, dist
├── .nvmrc                           ← `20.11.1`
├── index.html                       ← Vite HTML 진입점
├── package.json                     ← 정확한 버전 고정 (§3)
├── package-lock.json                ← 커밋 필수
├── tsconfig.json                    ← strict: true, paths alias
├── tsconfig.node.json               ← Vite 설정용 tsconfig
├── vitest.config.ts                 ← Vitest 설정 (§7.4)
├── vite.config.ts                   ← dev 서버 포트·프록시 설정
├── tailwind.config.ts
├── postcss.config.js
├── CLAUDE.md                        ← AI 컨텍스트 기준 파일 (최신 버전)
└── README.md                        ← 사람 대상 진입점 (실행 방법·구조 요약)
```

---

## 3. 기술 스택 및 버전 고정

모든 패키지는 `package.json`에 **정확한 버전**(예: `"react": "18.3.1"`)으로 명시한다. 버전 범위 연산자(`^`, `~`, `>=`) 사용 금지.

| 패키지 / 도구 | 버전 | 출처 |
|---|---|---|
| Node.js | 20.11.1 (LTS) | 본 Frame 명세 §3 단독 정의 |
| npm | 10.2.4 | Node 20.11.1 번들 |
| react | 18.3.1 | web_plan_v6 §11.1 (메이저 18) + 본 Frame 패치 확정 |
| react-dom | 18.3.1 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| typescript | 5.4.5 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| vite | 5.2.11 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| @vitejs/plugin-react | 4.3.0 | 본 Frame 명세 §3 단독 정의 (Vite React 지원) |
| tailwindcss | 3.4.3 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| postcss | 8.4.38 | 본 Frame 명세 §3 단독 정의 (Tailwind 요구) |
| autoprefixer | 10.4.19 | 본 Frame 명세 §3 단독 정의 (Tailwind 요구) |
| d3 | 7.9.0 | web_plan_v6 §11.1 (D3.js v7) + 본 Frame 패치 확정 |
| @types/d3 | 7.4.3 | 본 Frame 명세 §3 단독 정의 (D3 타입 정의) |
| zustand | 4.5.2 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| react-router-dom | 6.23.0 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| axios | 1.6.8 | web_plan_v6 §11.1 + 본 Frame 패치 확정 |
| @tanstack/react-query | 5.32.0 | 본 Frame 명세 §3 단독 정의 (web_plan_v6 §11.1 미명시) |
| date-fns | 3.6.0 | 본 Frame 명세 §3 단독 정의 (web_plan_v6 §11.1 미명시) |
| vitest | 1.6.0 | 본 Frame 명세 §3 단독 정의 (smoke test §7.4) |
| @testing-library/react | 15.0.6 | 본 Frame 명세 §3 단독 정의 (smoke test §7.4) |
| @testing-library/jest-dom | 6.4.5 | 본 Frame 명세 §3 단독 정의 (smoke test matchers) |
| jsdom | 24.0.0 | 본 Frame 명세 §3 단독 정의 (Vitest 브라우저 환경) |
| eslint | 8.57.0 | 본 Frame 명세 §3 단독 정의 (코드 품질) |
| @typescript-eslint/parser | 7.7.0 | 본 Frame 명세 §3 단독 정의 |
| @typescript-eslint/eslint-plugin | 7.7.0 | 본 Frame 명세 §3 단독 정의 |
| eslint-plugin-react-hooks | 4.6.0 | 본 Frame 명세 §3 단독 정의 |
| prettier | 3.2.5 | 본 Frame 명세 §3 단독 정의 |

> **고정 원칙**: 위 표의 모든 버전은 Frame 생성 시점(2026-04-24~28) 기준 안정 버전을 적용한다. 이 Frame 머지 이후 **feat/* 브랜치에서 버전을 임의로 상향·하향할 수 없다**. 변경이 필요하면 별도 Feature 명세를 작성하고 PM 승인을 받는다.
>
> **web_plan_v6 §11.1과의 관계**: web_plan_v6 §11.1은 메이저 버전(예: `React 18`, `D3.js v7`)까지만 명시한다. 본 Frame 명세는 이를 정확한 패치 버전으로 고정하고, web_plan에 부재한 패키지(@tanstack/react-query, date-fns, ESLint, Vitest 등)를 단독으로 확정한다.
>
> **PM 승인 사항**: §3 표의 패치 버전이 npm 레지스트리에서 설치 가능한지 PM 승인 시 확인.

---

## 4. 환경 변수 목록

프론트엔드 환경 변수는 Vite 규칙에 따라 `VITE_` 접두어를 사용한다. `.env.example`에 아래 변수를 모두 포함하고, `.env`는 `.gitignore`로 제외한다.

| 변수명 | 설명 | 필수 | 기본값 | 누락 시 동작 | 예외 코드 매핑 |
|---|---|:---:|---|---|---|
| `VITE_API_BASE_URL` | 백엔드 API Base URL (api_spec_v4 §공통 사항 Base URL과 일치) | 필수 | `http://localhost:8000/api/v1` | `console.error` 출력 후 빈 baseURL로 진행, Axios 호출 시 네트워크 에러 발생 | 해당 없음 (프론트 런타임 처리) |
| `VITE_USE_MOCK` | 목업 응답 사용 여부 (상세 §8.1) | 선택 | `true` | 미설정 시 `true`로 간주 | 해당 없음 |
| `VITE_APP_TITLE` | 브라우저 탭 타이틀 | 선택 | `가격 전달 이상 탐지` | 미설정 시 기본값 사용 | 해당 없음 |

> **예외 코드 매핑 정책**: `exception_spec_v2`의 `CFG-CORE-*` 코드는 백엔드(Python) 부팅 시 예외에 한정된다(동 문서 §6 기준). 프론트엔드 환경 변수 누락은 위 표의 "누락 시 동작"에 정의된 방식으로 처리하며 신규 예외 코드를 정의하지 않는다.
>
> **시크릿 금지**: 프론트엔드 환경 변수는 빌드 시 번들에 포함되어 브라우저에서 노출된다. DB 접속 정보·API 키·JWT 시크릿을 기재하지 않는다. 백엔드 전용 변수(`DATABASE_URL`, `REDIS_URL`, `CORS_ALLOWED_ORIGINS`, `ROLLING_WINDOW`, `CONTAMINATION`, `RANDOM_STATE`)는 본 파일에 포함하지 않는다.

---

## 5. DB 연결 방식

> 템플릿 규칙에 따라 프론트엔드 Frame 명세에서는 본 섹션을 삭제한다. DB 연결은 백엔드 Frame 명세(`docs/frame_spec_backend_*.md`)의 §5를 참조한다.

---

## 6. 타입 정의 파일 위치

| 항목 | 경로 | 대응 관계 |
|---|---|---|
| 백엔드 Pydantic 스키마 | `app/schemas/` (백엔드 repo) | `api_spec_v4.md` response 1:1 대응 |
| 프론트엔드 TypeScript 타입 | `src/types/` | 백엔드 Pydantic 스키마 1:1 대응 |
| 검증 시점 | `frame/frontend → dev` 머지 직전 PM 게이트 (sprint_plan §10 "S1 후반 완료") | PM이 §6.2 표를 3방향 대조하여 일치 확인 (Literal 값 포함) |

### 6.1 필드명 표기 정책

API 응답 JSON 키를 변형 없이 `snake_case`로 그대로 사용한다.

- **근거**: `team_ai_collab_v6 §3.3` "필드명 드리프트 방지" 원칙. DB 컬럼명이 snake_case이므로 API·TypeScript도 동일 표기.
- **구현 제약**: Axios 응답 변환 인터셉터·유틸 함수 작성 금지. ESLint `camelcase` 규칙은 `properties: "never"` 옵션으로 객체 프로퍼티 snake_case를 허용한다.
- **프론트 내부 변수·함수명**: TypeScript 표준 관례에 따라 camelCase를 사용한다(객체 프로퍼티만 예외).

### 6.2 3방향 필드명·타입 일치 필수 확인 목록

`frame/frontend → dev` 머지 직전 PM이 `db_schema_v3.md` → `api_spec_v4.md` → `src/types/*.ts` 순으로 대조하여 불일치 0건을 확인한다.

| db_schema_v3 컬럼 / 정책 | api_spec_v4 JSON 키 | TypeScript 타입 |
|---|---|---|
| `commodity_id` | `commodity_id` | `commodity_id: string` |
| `segment_id` | `segment_id` | `segment_id: string` |
| `period` (DATE 월초) | `period` (`YYYY-MM`) | `period: string` (§6.5 형식 검증) |
| `cluster` | `cluster` | `cluster: 'grain' \| 'oil_sugar' \| 'tropical' \| 'livestock' \| 'independent'` |
| `route_type` | `route_type` | `route_type: '3seg' \| '4seg'` |
| `confidence_grade` | `confidence_grade` | `confidence_grade: 'high' \| 'medium' \| 'reference'` |
| `primary_pattern` | `primary_pattern` | `primary_pattern: 'pattern1' \| 'pattern2' \| 'pattern3'` |
| `pattern_types` (배열) | `pattern_types` (배열) | `pattern_types: ('pattern1' \| 'pattern2' \| 'pattern3')[]` |
| `model_params.model_type` | `segment_meta.{seg}.model_type` | `model_type: 'VAR' \| 'VECM'` |
| `stat_timeseries.ect_type` | `ect_type` (패널 응답) | `ect_type: 'ECT' \| 'log_spread' \| null` |
| `transmission_rate` | `transmission_rate` | `transmission_rate: number \| null` |
| `is_new` | `is_new` | `is_new: boolean` |
| `anomaly_id` (← `anomaly_results.id`) | `anomaly_id` | `anomaly_id: number` |
| `pipeline_runs.status` (내부) | (응답 미노출) | (내부 필드 — 프론트엔드 미수신) |
| (envelope) | `granularity` | `granularity: 'monthly' \| 'quarterly' \| 'yearly'` |
| (envelope) | `requested_from`/`requested_to`/`actual_from`/`actual_to` | `string` (`YYYY-MM`, §6.5) |
| (envelope) | `total_points` | `total_points: number` |

> **OI-15 미결**: `src/types/anomaly.ts`의 `ml_projections.projection_method`는 `'pca' \| 'feature_direct'` 유니온 타입으로 선언한다. S4에서 확정 후 feat 브랜치에서 단순화한다.

### 6.3 Literal 타입 사용 원칙

고정 enum 성격의 문자열 필드는 **TypeScript 리터럴 유니온 타입**으로 선언한다.

- **값 목록 출처**: `db_schema_v3`의 컬럼 코멘트 (예: `'high' | 'medium' | 'reference'`).
- **단일 출처(SoT)**: `src/types/literals.ts`에 상수 배열 + 유니온 타입을 함께 export한다. 다른 타입 파일은 `literals.ts`의 타입을 import하여 재사용한다.

```ts
// src/types/literals.ts (요지)
export const CONFIDENCE_GRADES = ['high', 'medium', 'reference'] as const;
export type ConfidenceGrade = typeof CONFIDENCE_GRADES[number];

export const PRIMARY_PATTERNS = ['pattern1', 'pattern2', 'pattern3'] as const;
export type PrimaryPattern = typeof PRIMARY_PATTERNS[number];

// 이하 cluster, route_type, model_type, ect_type, granularity 동일 패턴
```

- **사용 제약**: 같은 유니온을 두 군데에 직접 선언 금지(드리프트 방지).
- **DB CHECK 제약 부재 보완**: db_schema_v3은 CHECK 제약을 두지 않으므로 백엔드는 Pydantic Literal로, 프론트는 TypeScript 리터럴 유니온으로 입출력 양쪽을 강제한다.

### 6.4 에러 응답 envelope 스키마

`api_spec_v4 §공통 사항` + `exception_spec_v2 §부록 A` 정책에 따른 응답 형식. 모든 4xx·5xx 응답은 본 envelope를 따른다.

```ts
// src/types/error.ts
export interface ApiErrorBody {
  code: string;        // 외부 코드 (예: 'COMMODITY_NOT_FOUND', 'INVALID_SEGMENT', 'INTERNAL_ERROR')
  message: string;
  context?: Record<string, unknown>;  // D-20: 디버깅 컨텍스트 (검증 실패 필드, 요청 파라미터 등)
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}
```

- **외부 코드 목록**: `api_spec_v4 §에러 코드 정의` (13종) + `INTERNAL_ERROR` 1종.
- **인터셉터 동작**: `src/api/error.ts`에서 Axios 응답이 위 형식이면 `ApiError` 클래스로 래핑하여 throw. 형식이 아니면 `'NETWORK_ERROR'` 코드로 정규화.
- **신규 코드 추가 금지**: 명세 8종에 부재한 외부 에러 코드를 임의로 생성하지 않는다.

### 6.5 날짜·시각 역직렬화 정책

백엔드는 `api_spec_v4 §공통 사항 D-11` 정책으로 날짜를 직렬화한다. 프론트엔드는 그 형식을 그대로 수신하고, 차트·필터에서 필요할 때만 `date-fns`로 파싱한다.

| 필드 종류 | 수신 형식 | TypeScript 타입 | 파싱 시점 |
|---|---|---|---|
| `period` (DATE 월) | `YYYY-MM` (예: `"2026-03"`) | `string` | 차트 x축·필터 비교 시 `parse(s, 'yyyy-MM', new Date())` |
| `start_date` / `end_date` 등 (DATE 일) | `YYYY-MM-DD` (예: `"2022-02-15"`) | `string` | 동일 |
| `created_at` / `last_updated` 등 (TIMESTAMPTZ) | ISO 8601 UTC `Z` (예: `"2026-04-01T03:00:00Z"`) | `string` | `parseISO(s)` |

> **타입 정책**: 모든 날짜·시각 필드는 TypeScript에서 `string`으로 받아 그대로 보관한다. `Date` 객체로 자동 변환하는 인터셉터·유틸 작성 금지. 변환은 사용 시점에 명시적으로 한다.

---

## 7. 로컬 실행 확인 기준

### 7.1 사전 준비

- [ ] Node.js 20.11.1 설치 확인 (`node -v` 출력이 `v20.11.1`, `.nvmrc` 일치)
- [ ] `npm install` 성공 (`package-lock.json` 생성)
- [ ] `.env.example`을 복사하여 `.env` 생성, `VITE_USE_MOCK=true`로 설정
- [ ] `docs/` 폴더 내 명세 8종 + CLAUDE.md 사본 9개 파일 존재

### 7.2 fixtures 필드 구조 검증

`src/fixtures/`의 각 JSON은 대응 API 엔드포인트 응답 구조와 일치해야 한다.

- [ ] `commodities.json` 배열 길이 10 (db_schema_v3 §commodities 초기 데이터 10행과 일치)
- [ ] `commodities.json` 각 객체에 `commodity_id`, `cluster`, `route_type` 필드 포함, `cluster` 값은 §6.3 Literal 5종 중 하나
- [ ] `segments.json` 배열 길이 5 (db_schema_v3 §segments 초기 데이터 5행과 일치)
- [ ] `events.json` 배열 길이 5 (db_schema_v3 §external_events 초기 데이터 5행과 일치)
- [ ] `freshness.json`에 `data_up_to`, `next_run_date`, `last_updated` 필드 포함

### 7.3 실행 확인

- [ ] `npm run dev` 오류 없이 `http://localhost:5173`에서 dev 서버 기동
- [ ] 브라우저 접속 시 헤더·필터 바·메인 영역·우측 패널 자리 표시자 렌더링
- [ ] `App.tsx` 마운트 시 `commodities.json`을 반환하는 모의 요청 1회 실행, 콘솔에 응답 출력 (배열 길이 10, 각 행 `commodity_id`/`cluster`/`route_type` 키 존재)
- [ ] `npm run build` 오류 없음 (TypeScript strict 컴파일 통과, `dist/` 생성)
- [ ] `npm run lint` 경고 0건
- [ ] `npm run format:check` 위반 0건
- [ ] `npm run test` 실행 시 §7.4 smoke test 3건 통과

### 7.4 Frame 단계 smoke test 범위

`tests/frame_smoke.test.ts`에 다음 3건만 작성한다. UI 인터랙션·D3 렌더링·실 API 통합 테스트는 모두 feat 단계.

1. **`test_app_renders`**: `@testing-library/react`로 `<App />` 마운트, 헤더·필터 바·메인 영역·우측 패널 자리 표시자 4개 모두 DOM 존재 확인.
2. **`test_commodities_mock_response`**: `VITE_USE_MOCK=true` 상태에서 `client.get('/commodities')` 호출 → 응답이 길이 10 배열, 각 행에 `commodity_id`·`cluster`·`route_type` 키 존재, `cluster`는 §6.3 Literal 5종 중 하나, `route_type`은 `'3seg'` 또는 `'4seg'`.
3. **`test_literal_types_consistency`**: `src/types/literals.ts`의 모든 상수 배열(`CONFIDENCE_GRADES`, `PRIMARY_PATTERNS`, `CLUSTERS`, `ROUTE_TYPES`, `MODEL_TYPES`, `ECT_TYPES`, `GRANULARITIES`)이 테스트 파일 내에 하드코딩된 기대값 객체(§6.2 표를 기준으로 작성)와 deep equal로 일치하는지 검증.

### 7.5 npm 스크립트

| 스크립트 | 명령 | 용도 |
|---|---|---|
| `dev` | `vite` | dev 서버 기동 |
| `build` | `tsc -b && vite build` | 프로덕션 빌드 |
| `preview` | `vite preview` | 빌드 결과물 미리보기 |
| `test` | `vitest run` | 전체 테스트 (smoke test 포함) |
| `test:watch` | `vitest` | 테스트 watch 모드 |
| `lint` | `eslint . --ext ts,tsx --max-warnings 0` | ESLint 검사 |
| `format` | `prettier --write .` | Prettier 자동 포맷 |
| `format:check` | `prettier --check .` | Prettier 검증 |

---

## 8. 기타

### 8.1 더미 응답 정책 (`VITE_USE_MOCK` 동작 정의)

백엔드 Frame 머지 전 로컬 실행 검증을 위해 `src/fixtures/` 정적 JSON 파일을 사용한다. msw(Mock Service Worker)는 도입하지 않는다.

| 환경 변수 값 | 동작 |
|---|---|
| `VITE_USE_MOCK=true` | `src/api/client.ts` 요청 인터셉터가 실제 HTTP 요청을 가로채고 `src/fixtures/` JSON을 반환한다. 백엔드 서버 가동 여부와 무관하게 단독 실행 가능. |
| `VITE_USE_MOCK=false` | 인터셉터를 비활성화하고 `VITE_API_BASE_URL`로 실제 HTTP 요청을 전송한다. |
| 미설정 | `true`로 간주 (§4 누락 시 동작). |

**더미값 출처는 명시적으로 명세 문서를 참조**하며 임의 창작 금지.

| 엔드포인트 | 더미값 출처 |
|---|---|
| `GET /api/v1/commodities` | **db_schema_v3 §`commodities` 초기 데이터 표 (10행)** 그대로 |
| `GET /api/v1/segments` | **db_schema_v3 §`segments` 초기 데이터 표 (5행)** 그대로 |
| `GET /api/v1/events` | **db_schema_v3 §`external_events` 초기 데이터 표 (5행)** 그대로 |
| `GET /api/v1/freshness` | 고정값 `{"data_up_to": "2026-03", "next_run_date": "2026-04-15", "last_updated": "2026-04-01T03:00:00Z"}` (백엔드 Frame 명세 §8.1과 일치) |
| 그 외 엔드포인트 | feat 단계에서 fixtures 추가 |

### 8.2 API 경로 정책

api_spec_v4 §공통 사항이 `Base URL = /api/v1`을 명시한다. 본 Frame 명세는 다음을 확정한다.

- `src/api/endpoints.ts`에 모든 엔드포인트를 상수로 선언한다 (예: `COMMODITIES_LIST = '/commodities'`).
- Axios `baseURL`은 `VITE_API_BASE_URL`(기본 `http://localhost:8000/api/v1`)로 설정하여, 호출 시점에는 `/commodities`처럼 prefix 없이 호출한다.
- 프록시 경로(`/api/v1`) 사용 여부는 `feat/api-endpoints` 브랜치에서 결정한다 (§8.3 참조).

### 8.3 CORS 처리

개발 환경에서 프론트엔드(`:5173`)와 백엔드(`:8000`)가 다른 포트로 동작한다. 백엔드 Frame 명세 §8.10에 따라 백엔드 측 `CORS_ALLOWED_ORIGINS` 기본값은 `http://localhost:5173`이다.

- **프록시 미사용 (기본)**: Axios가 `http://localhost:8000/api/v1`로 직접 요청한다. 백엔드의 CORS 미들웨어가 `localhost:5173`을 허용하므로 정상 동작한다.
- **프록시 사용 (선택)**: `vite.config.ts`에서 `/api`를 백엔드로 프록시한다.

```ts
// vite.config.ts (요지)
server: {
  port: 5173,
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true }
  }
}
```

`.env.example`의 `VITE_API_BASE_URL` 기본값은 절대 URL(`http://localhost:8000/api/v1`)로 둔다. 프록시 사용 전환 시 상대 경로(`/api/v1`)로 변경한다.

### 8.4 ESLint·Prettier 도구 설정

```js
// .eslintrc.cjs 요지
module.exports = {
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'react-hooks'],
  rules: {
    'camelcase': ['error', { properties: 'never' }],   // §6.1 정책
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
};
```

```json
// .prettierrc
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100
}
```

### 8.5 Vitest 설정

```ts
// vitest.config.ts (요지)
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
  },
});
```

- `tests/setup.ts`에서 `@testing-library/jest-dom` matchers 등록.
- `VITE_USE_MOCK`은 테스트 환경에서 항상 `true`.

### 8.6 D3.js 시각화 구현 범위 (Frame 비포함)

D3.js 기반 시각화(스트림 그래프·산점도·원시 시계열·IRF·ML 결과맵·미니맵)는 본 Frame에서 **구현하지 않는다**. 본 Frame은 `d3@7.9.0`, `@types/d3@7.4.3` 패키지 설치와 `src/components/charts/.gitkeep` 빈 폴더 생성까지만 책임진다.

후속 feat 브랜치 분할:

| feat 브랜치 | 구현 컴포넌트 |
|---|---|
| `feat/stream-chart` | 스트림 그래프 |
| `feat/scatter-chart` | 산점도 |
| `feat/raw-timeseries` | 원시 시계열 차트 |
| `feat/analysis-panel` | IRF 차트 + 분석 수치 패널 |
| `feat/ml-map` | ML 결과맵 (OI-15 확정 후) |
| `feat/minimap` | 연도별 이상 밀도 미니맵 |

### 8.7 `src/services/` 향후 분할 예고

Frame 단계는 `src/services/.gitkeep` 빈 상태 유지. 후속 feat 브랜치에서 데이터 변환·집계 로직을 추가한다.

```
src/services/
├── timeseries.ts       ← API 시계열 응답 → D3 입력 변환 (feat/stream-chart)
├── anomaly.ts          ← 이상 탐지 패널용 데이터 집계 (feat/analysis-panel)
└── filter.ts           ← 필터 상태 → API 쿼리 파라미터 변환 (feat/filter-bar)
```

### 8.8 담당 체계

- **Frame 작성·구현·PR 제출**: 하대수 (sprint_plan §3.2)
- **후속 feat 단계 프론트엔드 협업자**: 하대수 (전체 UI·상태관리 주도, sprint_plan §4~7), 바게스타니 샤킬라 (분석 수치 패널·온보딩 영역, sprint_plan §6~7)

### 8.9 플랫폼 범위

데스크탑 웹 환경을 대상으로 한다 (web_plan_v6 §1.3). 모바일 반응형은 1차 출시 범위 외 (web_plan_v6 §14).

### 8.10 절대 금지 사항

| 금지 사항 | 이유 |
|---|---|
| `package.json`에 버전 범위 연산자(`^`, `~`, `>=`) 사용 | 재현성 파괴 |
| `localStorage`, `sessionStorage` 사용 | 1차 출시 정책 — 세션 상태는 Zustand 메모리 기반으로만 관리 |
| API 응답 필드명을 camelCase로 변환하는 인터셉터·유틸 함수 작성 | §6.1 정책 위반, 3방향 일치 파괴 |
| 백엔드 전용 환경 변수(`DATABASE_URL` 등)를 `.env.example`에 추가 | §4 책임 분리 위반 |
| Axios 응답 `period` 필드를 자동으로 `Date` 객체로 변환 | §6.5 정책 위반 |
| 동일 Literal 유니온을 `literals.ts` 외 파일에 직접 선언 | §6.3 SoT 정책 위반, 드리프트 발생 |
| 명세 8종에 부재한 외부 에러 코드를 `src/api/error.ts`에서 임의 정의 | §6.4 위반, exception_spec_v2 §8 규칙 위반 |
| `src/components/charts/`에 Frame 단계 D3 컴포넌트 작성 | §8.6 위반 |
| `src/services/`에 Frame 단계 비즈니스 로직 작성 | §8.7 위반 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 디렉토리 구조가 db_schema_v3·api_spec_v4와 정합한가 | ☐ |
| 패키지 버전이 전체 고정되어 있는가 (버전 범위 연산자 0건) | ☐ |
| §3 표의 패치 버전이 npm 레지스트리에서 설치 가능한가 | ☐ |
| 필수 환경 변수가 모두 정의되어 있는가 | ☐ |
| 로컬 실행 확인 기준이 구체적인가 (smoke test 3건 포함) | ☐ |
| 타입 정의 3방향 일치 경로 + Literal 값 목록이 명시되어 있는가 | ☐ |
| 명세 8종 + CLAUDE.md `docs/` 폴더 첨부 정책이 명시되어 있는가 | ☐ |
| 더미 응답 출처가 db_schema_v3 §초기 데이터로 명시되어 있는가 | ☐ |
| 에러 응답 envelope 스키마가 api_spec_v4·exception_spec_v2와 일치하는가 | ☐ |

**승인일**: YYYY-MM-DD
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `frame/frontend` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: frame/frontend
- **Frame 명세**: `docs/frame_spec_frontend_v3.md`
- **담당자**: 하대수

## 구현 완료 항목
- [ ] 디렉토리 구조 생성 (§2)
- [ ] 기술 스택 버전 고정 — `package.json` 정확한 버전, 버전 범위 연산자 0건 (§3)
- [ ] 환경 변수 `.env.example` 작성 (§4)
- [ ] Axios 인스턴스 + MOCK 분기 + 에러 인터셉터 (§4, §6.4, §8.1)
- [ ] TypeScript 타입 정의 + Literal 상수 (§6, §6.3)
- [ ] 에러 envelope 타입 + ApiError 클래스 (§6.4)
- [ ] fixtures 4종 작성 (§7.2, §8.1)
- [ ] 로컬 실행 확인 (§7.3)
- [ ] Smoke test 3건 통과 (§7.4)

## 3방향 타입 일치 확인
- [ ] `db_schema_v3.md` ↔ `api_spec_v4.md` ↔ `src/types/` 필드명 일치
- [ ] Literal 값 목록 일치 (`cluster`, `route_type`, `confidence_grade`, `primary_pattern`, `model_type`, `granularity`, `ect_type`)
- [ ] snake_case 필드명 유지 (§6.1, 변환 인터셉터 없음)
- 불일치 항목: {없음 / 목록}

## 포함된 문서
- [ ] `docs/` 폴더에 명세 8종 사본 첨부 (doc1_v9, doc3_v11, web_plan_v6, pipeline_output_spec_v5, db_schema_v3, api_spec_v4, exception_spec_v2, sprint_plan)
- [ ] `CLAUDE.md` 최신 버전 첨부
- [ ] `README.md` 초기 작성

## 로컬 실행 증빙
- `npm run dev` 실행 로그
- `http://localhost:5173` 빈 레이아웃 스크린샷
- 브라우저 콘솔의 `commodities.json` 응답 로그 (배열 길이 10, `commodity_id`/`cluster`/`route_type` 키 확인)
- `npm run test` smoke test 3건 통과 로그
- `npm run build` 성공 로그
- `npm run lint`, `npm run format:check` 통과 로그

## 리뷰어 확인 요청 사항
- snake_case 필드명 정책 최종 승인 (§6.1)
- Literal 타입 SoT 정책 최종 승인 (§6.3 — `literals.ts` 단일 출처)
- 더미 응답 출처 정책 (db_schema_v3 §초기 데이터 직접 사용) 최종 승인 (§8.1)
- D3 컴포넌트 구현 범위 분할 (§8.6) 최종 승인

## 기타
- D3 시각화 미구현 (§8.6)
- `src/services/` Frame 단계 비포함 (§8.7)
```
