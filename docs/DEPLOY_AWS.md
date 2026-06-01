# AWS 배포 검토

> 본 문서는 **검토·옵션 비교**용이다. 실제 배포 산출물(Terraform/CloudFormation/CI)은 포함하지 않는다.
> 로컬 컨테이너화 자산(`Dockerfile`, `docker-compose.yml`, `db/snapshot.sql.gz`)은 그대로 재사용한다.

## 전제

- 서빙 app은 **상태가 없고 DB에서만 읽는다** → 수평 확장·재배포가 자유롭다.
- 데이터는 `db/snapshot.sql.gz` 한 파일로 이식된다 (스키마+데이터+alembic_version).
- 의존성: PostgreSQL 16, Redis 7. Redis는 다운돼도 graceful degradation(캐시만 비활성).
- 이미지 빌드는 배포 아키텍처에 맞춰 **`--platform linux/amd64`** (Apple Silicon에서 빌드 시 주의).

---

## 옵션 비교

| 항목 | A. EC2 + docker compose | B. ECS Fargate + RDS + ElastiCache | C. App Runner |
|---|---|---|---|
| 한 줄 요약 | compose 그대로 lift-and-shift | 관리형 컨테이너 + 관리형 DB/캐시 | app 컨테이너만 초간단 배포 |
| 멀티 컨테이너 | O (db/redis/app 한 호스트) | O (태스크/서비스 분리) | **X** (단일 컨테이너) → DB/Redis 외부 필수 |
| 운영 난이도 | 낮음 (단, 호스트 직접 관리) | 중 (IaC·네트워킹 설계) | 가장 낮음 |
| 데이터 영속성 | EBS 볼륨 (직접 백업) | RDS 자동 백업·스냅샷 | RDS 필요 |
| 비용(개략) | t3.small ~월 $15 + EBS | Fargate + RDS + ElastiCache 합산 ↑ | App Runner + RDS |
| 적합 | **데모·발표·저비용** | **운영·고가용성** | app만 빠르게 띄울 때 |

### A. EC2 + docker compose (권장: 데모/발표)
1. EC2(Amazon Linux 2023, t3.small+) 기동, Docker + compose 플러그인 설치.
2. 레포 클론 또는 app 이미지를 ECR에서 pull, `db/snapshot.sql.gz` 동봉.
3. `.env` 작성 후 `docker compose up -d` — 로컬과 동일.
4. 보안그룹에서 8001 개방(또는 앞단에 Nginx/ALB + TLS).
- user-data 스크립트로 1~3을 부팅 시 자동화 가능.
- 단점: 단일 호스트 SPOF, OS 패치 자체 관리.

### B. ECS Fargate + RDS + ElastiCache (권장: 운영)
1. app 이미지 → **ECR** push (`linux/amd64`).
2. **RDS for PostgreSQL 16** 생성 → 스냅샷 복원:
   `gunzip -c snapshot.sql.gz | psql -h <rds-endpoint> -U <user> -d price_transmission`
   (또는 EC2 bastion 경유). 이후 마이그레이션은 app 태스크의 `alembic upgrade head`가 처리.
3. **ElastiCache for Redis** 생성.
4. ECS 서비스(Fargate)로 app 태스크 실행, `DATABASE_URL`/`REDIS_URL`은 각 엔드포인트로.
5. 앞단 ALB(헬스체크 경로 `/api/v1/meta/config`) + ACM TLS.
- `compose` → ECS 변환은 보통 수동 task definition 작성(또는 `ecs-cli`/Copilot).
- 장점: 관리형 백업·확장·다중 AZ.

### C. App Runner
- app 컨테이너만 ECR→App Runner로 가장 간단히 배포. 헬스체크 `/api/v1/meta/config`.
- 멀티 컨테이너 불가 → **RDS(Postgres) + ElastiCache(Redis) 외부 의존 필수**. 사실상 B의 DB/캐시 구성 + app만 App Runner로 대체한 형태.

---

## 횡단 고려사항

- **시크릿**: `.env`의 `DATABASE_URL` 등 → SSM Parameter Store / Secrets Manager로 주입(이미지/코드에 굽지 않음).
- **이미지 레지스트리**: ECR. 태그는 git SHA 권장.
- **APP_ENV**: 운영은 `production` (DB/Redis 실패 시 기동 중단 — fail-fast).
- **워커 수**: 현재 entrypoint는 `--workers 1` (APScheduler 중복 기동 방지). 수평 확장은 컨테이너 replica로, 배치 스케줄러는 단일 인스턴스에만 두도록 분리 필요.
- **스냅샷 크기**: git 커밋 한계(~50MB) 초과 시 S3 + 부팅 시 다운로드 또는 RDS 스냅샷으로 전환.
- **CI/CD(추후)**: GitHub Actions → ECR push → ECS 서비스 업데이트. 본 문서 범위 외.

## 권장 경로

- **발표/데모**: A (EC2 + compose). 로컬과 100% 동일, 추가 학습 비용 최소.
- **운영 전환 시**: B (ECS Fargate + RDS + ElastiCache). 데이터 영속성·확장·백업 확보.
