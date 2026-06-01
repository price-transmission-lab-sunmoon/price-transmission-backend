# 서빙 전용 app 이미지 — DB에서만 읽으므로 data/·pipeline/ 불포함.
FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 — 코드 변경 시 재설치 안 함)
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 서빙에 필요한 코드만 복사
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini pyproject.toml ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8001

# slim 이미지에 curl 없음 → 표준 라이브러리로 헬스체크
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/api/v1/meta/config',timeout=3).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
