# docs_manifest — 명세 문서 버전·참조 맵 (단일 출처)

**목적**: `docs/` 내 모든 명세 문서의 **현재 최신 버전**과 **문서 간 참조 관계**를 단일 파일에서 관리한다. 다른 명세 문서는 본 파일을 조회하여 `abcd_vN.md` 규칙의 `vN`을 해석한다. 상위 명세가 갱신되면 **본 파일의 §1 버전 해석표 한 줄만 고치면** 전체 문서의 참조가 자동으로 최신을 가리키도록 설계되어 있다.

**파일 정책**: 본 파일은 **버전을 붙이지 않는다** (`docs_manifest.md`). 자기 자신이 SoT이므로 버전 개념이 모순이기 때문.

**작성일**: 2026-05-02
**관리자**: PM 최수안
**근거**: `reference_audit_report v1` §4 (vN 표기 규칙 도입 배경)

---

## 1. 버전 해석표 (Version Resolution Table)

> **이 표가 SoT다.** 모든 명세 문서 본문의 `_vN` 표기는 본 표의 "현재 버전" 열로 해석된다. 버전이 바뀌면 해당 행만 수정하면 되며, 하위 참조 문서의 본문을 일괄 수정할 필요가 없다.

| 문서 ID (키) | 현재 버전 | 실제 파일명 | 문서 설명 |
|---|---|---|---|
| `doc1_technical_pipeline` | **v10** | `doc1_technical_pipeline_v10.md` | 파이프라인 Phase 0~9 기술 명세 (루트 권위) |
| `doc2_pattern_definitions` | **v2** | `doc2_pattern_definitions_v2.md` | 패턴 정의 (루트 권위) |
| `doc3_research_proposal` | **v11** | `doc3_research_proposal_v11.md` | 연구 제안서 (루트 권위) |
| `web_plan` | **v6** | `web_plan_v6.md` | 웹 서비스 기획서 (루트 권위) |
| `pipeline_output_spec` | **v9** | `pipeline_output_spec_v9.md` | 파이프라인 출력 명세 |
| `db_schema` | **v6** | `db_schema_v6.md` | PostgreSQL DB 스키마 명세 |
| `api_spec` | **v6** | `api_spec_v6.md` | FastAPI 엔드포인트 명세 |
| `exception_spec` | **v6** | `exception_spec_v6.md` | 예외 코드 인덱스 (반복 조회용) |
| `exception_design` | **v3** | `exception_design_v3.md` | 예외 체이닝 설계 (심층 분석용) |
| `feature_dev_list` | **v5** | `feature_dev_list_v4.md` | feat/* 브랜치 기능 개발 목록 |
| `frame_spec_backend` | **v5** | `frame_spec_backend_v4.md` | 백엔드 Frame 명세 |
| `frame_spec_frontend` | **v5** | `frame_spec_frontend_v5.md` | 프론트 Frame 명세 |
| `sprint_plan` | _(미입고)_ | _(파일 부재)_ | 스프린트 계획 — 현 repo에 미동기화 |
| `team_ai_collab` | _(미입고)_ | _(파일 부재)_ | 팀 AI 협업 규칙 — 현 repo에 미동기화 |

### 1.1 미입고 문서의 취급

`sprint_plan` / `team_ai_collab` 은 본 백엔드 repo 로컬에 파일은 없지만 본문에서 참조된다. §2.2 **파일 부재 방지 규칙**에 따라 해당 문서를 참조해야 하는 작업은 **파일 보충 전까지 진행 금지**한다. 보충 방법: 상위 팀 레포에서 최신본을 `docs/`로 복사 후 본 표에 `현재 버전` 및 `실제 파일명` 채움.

---

## 2. 운영 규칙

### 2.1 버전 해석 규칙 (모든 문서에 적용)

- **본문·헤더의 `_vN` 표기**는 항상 본 문서 §1 표를 통해 해석한다
- **구체 버전(예: `api_spec_v5`) 하드코딩 금지**. 단 아래 예외:
  1. 변경 이력 항목 — 그 시점의 구체 버전을 그대로 남긴다 (`당시 db_schema v3` 등)
  2. 자기 자신의 버전 레이블 — 헤더 `(v5)`, 푸터 `*v5 —` 는 파일명과 일치시킨다
  3. 본 manifest §1 버전 해석표 (SoT이므로 여기서는 당연히 구체 버전 사용)
  4. 클릭 가능한 링크가 필요한 README / PR 본문 등 외부 진입점 (§4 참조)

### 2.2 파일 부재 방지 규칙 ⚠️ **(필수 안전 규칙)**

> **본 문서 §1 표에 명시된 버전의 실제 파일이 `docs/`에 존재하지 않으면, AI·사람 모두 해당 문서 참조가 포함된 작업을 절대로 진행하지 않는다.**

이유: 누락된 명세 문서를 추정·창작해 가며 코딩하면 구버전 정의·임의 규정으로 인한 재작업·버그·팀 간 혼선이 발생한다. 본 규칙은 해당 사고의 최종 방어선이다.

**AI 어시스턴트 체크리스트** (코드·문서 작업 착수 전 **반드시** 수행):

1. 본 파일 §1 버전 해석표의 모든 "실제 파일명" 엔트리가 `docs/` 폴더에 실제로 존재하는지 확인
2. 존재하지 않는 파일이 하나라도 있으면:
   - 작업 즉시 **중단**
   - 사용자 / PM에게 누락 파일을 알리고 보충 요청
   - "추정·창작으로 진행 가능한지" 묻지 않는다 — **진행 자체가 규칙 위반**
3. 파일이 전부 존재하면 작업 진행. 각 참조마다 `vN` → 구체 버전 매핑 시 본 표 조회

**금지 행동**:
- 누락된 문서의 내용을 추측하여 코드 작성
- "임시로" `abcd_vN` 참조를 플레이스홀더로 둔 채 코드 머지
- 본 manifest 없이 docs 변경 (본 파일을 먼저 갱신한 뒤 파일 추가·변경)

### 2.3 버전 갱신 절차 (사람 수행)

새 버전 명세를 만들 때:

1. 새 파일 `docs/<id>_v<N+1>.md` 생성 (본문·헤더 `(vN+1)`·변경이력 추가)
2. **본 manifest §1 버전 해석표의 해당 행만 갱신** — `현재 버전`, `실제 파일명`
3. **본 manifest §3 참조 맵 재확인** — 해당 문서가 상위·하위로 무엇을 참조·참조받는지 영향 범위 식별
4. 구버전 파일 처리:
   - 최소 1버전은 `docs/` 에 유지 (대조 검토용)
   - 그 이전 버전은 `docs/archive/` 이동 또는 삭제 (git history 로 조회 가능)
5. 커밋 메시지 예: `chore(docs): bump db_schema v5→v6 + update manifest`

### 2.4 새 문서 추가 절차

1. 새 문서 파일 `docs/<new_id>_v1.md` 생성
2. 본 manifest §1 버전 해석표에 새 행 추가
3. 본 manifest §3 참조 맵의 forward / reverse 양쪽에 새 엔트리 추가
4. 해당 문서에서 다른 문서를 참조하면 반드시 `_vN` 표기 사용

### 2.5 문서 퇴역 절차

1. 본 manifest §1 버전 해석표에서 해당 행을 **삭제하지 않고** `퇴역 (retired)` 표기 + 사유 주석
2. §3 참조 맵에서 해당 문서로 향하는 링크가 없는지 확인. 있으면 상위 문서에서 참조 제거
3. 파일 자체는 `docs/archive/` 로 이동 (삭제 금지 — 역사 보존)

---

## 3. 참조 맵 (Reference Map)

### 3.1 Forward references — "이 문서가 참조하는 문서들"

버전 갱신 시 영향도 검토에 사용한다.

| 문서 ID | 외부 참조 대상 | 비고 |
|---|---|---|
| `doc1_technical_pipeline` | _(없음)_ | 루트 권위 문서 |
| `doc2_pattern_definitions` | _(없음)_ | 루트 권위 문서 |
| `doc3_research_proposal` | `sprint_plan_vN` | §9.3 내 참조 안내만 (본문 내용은 독립) |
| `web_plan` | _(없음)_ | 루트 권위 문서 |
| `pipeline_output_spec` | `doc1_technical_pipeline_vN`, `doc2_pattern_definitions_vN` | 헤더 `작성 기준` |
| `db_schema` | `doc1_technical_pipeline_vN`, `doc2_pattern_definitions_vN`, `web_plan_vN`, `pipeline_output_spec_vN` | 헤더 `작성 기준` |
| `api_spec` | `db_schema_vN`, `web_plan_vN`, `pipeline_output_spec_vN` | 헤더 `작성 기준` |
| `exception_spec` | `exception_design_vN`, `feature_dev_list_vN` | 체이닝 설계 및 브랜치별 코드 매핑 |
| `exception_design` | `exception_spec_vN` | 에러 코드 인덱스 참조 |
| `feature_dev_list` | `doc1_technical_pipeline_vN`, `doc2_pattern_definitions_vN`, `doc3_research_proposal_vN`, `sprint_plan_vN`, `api_spec_vN`, `web_plan_vN`, `db_schema_vN`, `pipeline_output_spec_vN`, `exception_spec_vN`, `frame_spec_backend_vN` | 각 feat 브랜치 참조 명세 |
| `frame_spec_backend` | `doc1_technical_pipeline_vN`, `doc3_research_proposal_vN`, `web_plan_vN`, `pipeline_output_spec_vN`, `db_schema_vN`, `api_spec_vN`, `exception_spec_vN`, `sprint_plan_vN`, `team_ai_collab_vN` | 헤더 `작성 기준` + 본문 다수 |
| `frame_spec_frontend` | `doc1_technical_pipeline_vN`, `doc3_research_proposal_vN`, `web_plan_vN`, `pipeline_output_spec_vN`, `db_schema_vN`, `api_spec_vN`, `exception_spec_vN`, `sprint_plan_vN`, `team_ai_collab_vN`, `frame_spec_backend_vN` | 헤더 `작성 기준` + 본문 다수 |

### 3.2 Reverse references — "이 문서가 바뀌면 재검토해야 할 하위 문서들"

상위 명세 버전을 올렸을 때, 본문 내용에 영향이 있을 수 있는 **하위 문서**를 즉시 찾기 위한 역방향 인덱스다. 버전 숫자만 바뀌는 갱신(오타 수정 등)은 영향이 없을 수 있으나, **설계 변경이 동반된 버전 갱신**은 아래 목록 문서들의 본문을 반드시 검토한다.

| 상위 문서 변경 시 | 하위 재검토 대상 |
|---|---|
| `doc1_technical_pipeline` | `pipeline_output_spec`, `db_schema`, `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `doc2_pattern_definitions` | `pipeline_output_spec`, `db_schema`, `feature_dev_list` |
| `doc3_research_proposal` | `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `web_plan` | `db_schema`, `api_spec`, `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `pipeline_output_spec` | `db_schema`, `api_spec`, `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `db_schema` | `api_spec`, `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `api_spec` | `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend` |
| `exception_spec` | `exception_design`, `frame_spec_backend`, `frame_spec_frontend`, `feature_dev_list` |
| `exception_design` | `exception_spec` (양방향) |
| `feature_dev_list` | `exception_spec` (브랜치별 코드 매핑 표) |
| `sprint_plan` | `feature_dev_list`, `frame_spec_backend`, `frame_spec_frontend`, `doc3_research_proposal` |
| `team_ai_collab` | `frame_spec_backend`, `frame_spec_frontend` |
| `frame_spec_backend` | `feature_dev_list`, `frame_spec_frontend` (feat/be-batch 등의 참조 명세) |
| `frame_spec_frontend` | _(없음. 하위 프론트 feat 브랜치 생성 시 본 맵에 추가)_ |

### 3.3 의존성 계층 요약

루트 → 하위 방향 계층 (`→` 는 "이 아래가 이 위를 참조한다"):

```
Layer 0 (루트 권위 문서):
  doc1_technical_pipeline    doc2_pattern_definitions    doc3_research_proposal    web_plan

                  ↓                        ↓                        ↓                   ↓

Layer 1 (1차 설계 문서):
  pipeline_output_spec ────────────────→ db_schema ────→ api_spec
                      ↓                       ↓              ↓
Layer 2 (구현 가이드):
              exception_spec ←→ exception_design          frame_spec_backend    frame_spec_frontend
                      ↓                                       ↓                         ↓
Layer 3 (작업 관리):
              feature_dev_list ←───────────────────────────── ─
                                          (+ sprint_plan, team_ai_collab 은 외부 입고)
```

**갱신 파급 원칙**: 낮은 Layer 의 문서가 바뀔수록 상위 Layer 재검토 범위가 넓어진다. 특히 Layer 0 루트 문서 변경은 전 하위 문서 재검토.

---

## 4. 외부 진입점 링크 정책

README.md, PR 본문, 외부 발표 자료 등 **클릭 가능한 링크가 필요한 곳**에서는 §1 표의 `실제 파일명` 을 사용한다 (예: `docs/api_spec_v5.md`). 그 외 명세 문서 본문에서는 `abcd_vN.md` 유지.

---

## 5. AI 어시스턴트 세션 시작 시 체크리스트

코드 작업 요청을 받으면 **첫 응답 전**에 다음을 수행한다.

1. `docs/docs_manifest.md` (본 파일) 읽기
2. §1 표의 모든 "실제 파일명"이 `docs/` 에 존재하는지 확인 (ls / glob)
3. 누락된 파일이 있으면 §2.2 규칙대로 **작업 중단 + 사용자 알림**
4. 작업 중 문서를 참조할 때마다 `_vN` → 구체 파일명을 본 표로 해석
5. 새 명세 문서를 만들거나 버전을 올리면 반드시 본 파일 §1·§3 동시 갱신

---

## 6. 변경 이력

- v1 (2026-05-02): 최초 작성. `reference_audit_report v1` §4 의 `abcd_vN.md` 규칙 채택과 함께 구축. 초기 버전 해석표 14개 엔트리 등록 (그 중 2개는 외부 레포 미입고 상태).
- v2 정오 (2026-05-11): \rame_spec_frontend\ §3.1 forward references에 \rame_spec_backend_vN\ 추가 (§5·§8.1·§8.3 직접 참조 반영). §3.2 \rame_spec_backend\ reverse references에 \rame_spec_frontend\ 추가 (이번 버전 불일치 발견 경위의 근본 원인 해소).
- v2 (2026-05-11): `exception_spec` v5→v6 갱신 (`feat/be-api-timeseries` `API-COM-002` 추가). `frame_spec_backend` v3→v4 갱신 (`exception_spec` v6 정합, 환경 변수 4종 추가, `PipelineError` 제거, 파일명·브랜치명 정정). `frame_spec_frontend` v4→v5 갱신 (`FEError` 클래스 §6.4 명시, 환경 변수 노트 4종 추가, 브랜치명 10건 정정).
- v2 정오 (2026-05-23): `pipeline_output_spec` v7 → v9 갱신 (contamination=0.08 확정, ml_consensus_count 컬럼명, asymmetry_results 보조 컬럼, spread_n2/n3/n6 bool 타입 반영).

---

*본 문서는 단일 출처(SoT)다. 다른 명세 문서의 "참조 기준" 헤더·`작성 기준` 항목이 본 파일보다 우선할 수 없다. 상위 명세 갱신 시 본 파일을 우선 갱신하고 하위 문서 본문은 §3 reverse map 의 영향 범위에서 선택적으로 검토한다.*
