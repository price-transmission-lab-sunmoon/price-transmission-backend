"""Phase 5 — granger_results 적재 + cointegration_results.granger_direction 갱신

feature_spec_DB-PIPELINE_v2 §2 입력 데이터 기준.
exception_design_v3 §2 에러 체이닝 패턴 준수.

컬럼명 매핑:
  segment  → segment_id
  best_lag → 적재 제외 (DB granger_results 에 없음)

적재 대상: 4구간 품목(groundnuts, banana, orange) 구간 C만 존재.
granger_direction UPDATE: Phase 5 단일 트랜잭션 내에서 cointegration_results 갱신.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.loader.base import _v, append_phase_to_run

logger = logging.getLogger(__name__)


async def load_granger_results(
    session: AsyncSession,
    run_id: int,
) -> int:
    """Phase 5 granger_results.csv → granger_results UPSERT
    + cointegration_results.granger_direction UPDATE.

    UNIQUE KEY: (commodity_id, segment_id, direction).
    Returns granger_results upserted row count.
    """
    csv_path = Path(settings.pipeline_data_root) / "phase5" / "granger_results.csv"
    if not csv_path.exists():
        raise DBError(
            "DB-TX-001",
            f"Phase 5 입력 파일 없음: {csv_path}",
            {"path": str(csv_path), "run_id": run_id},
        )

    df = pd.read_csv(csv_path)

    try:
        # ── granger_results UPSERT ────────────────────────────────────────────
        for _, row in df.iterrows():
            cid = str(row["commodity_id"])
            seg = str(row["segment"])
            direction = str(row["direction"])

            significant_raw = row.get("significant")
            if isinstance(significant_raw, str):
                significant_raw = significant_raw.lower() == "true"

            await session.execute(
                text("""
                    INSERT INTO granger_results (
                        commodity_id, segment_id, direction, max_lag,
                        f_stat, pvalue, significant, confirmed_direction,
                        pipeline_run_id
                    ) VALUES (
                        :commodity_id, :segment_id, :direction, :max_lag,
                        :f_stat, :pvalue, :significant, :confirmed_direction,
                        :pipeline_run_id
                    )
                    ON CONFLICT (commodity_id, segment_id, direction) DO UPDATE SET
                        max_lag = EXCLUDED.max_lag,
                        f_stat = EXCLUDED.f_stat,
                        pvalue = EXCLUDED.pvalue,
                        significant = EXCLUDED.significant,
                        confirmed_direction = EXCLUDED.confirmed_direction,
                        pipeline_run_id = EXCLUDED.pipeline_run_id
                """),
                {
                    "commodity_id": cid,
                    "segment_id": seg,
                    "direction": direction,
                    "max_lag": int(row["max_lag"]),
                    "f_stat": _v(row.get("f_stat")),
                    "pvalue": _v(row.get("pvalue")),
                    "significant": bool(significant_raw),
                    "confirmed_direction": _v(row.get("confirmed_direction")),
                    "pipeline_run_id": run_id,
                    # best_lag 는 DB granger_results 에 없으므로 적재 제외
                },
            )

        # ── cointegration_results.granger_direction UPDATE ────────────────────
        # 4구간 품목 구간 C: (commodity_id, segment_id='C') 기준으로 갱신.
        # 두 방향 행(ppi_to_wholesale, wholesale_to_ppi)의 confirmed_direction 은 동일값이므로
        # 첫 번째 non-null 값을 사용.
        granger_map: dict[tuple[str, str], str | None] = {}
        for _, row in df.iterrows():
            key = (str(row["commodity_id"]), str(row["segment"]))
            cd = _v(row.get("confirmed_direction"))
            if cd is not None and key not in granger_map:
                granger_map[key] = cd

        for (cid, seg), confirmed_direction in granger_map.items():
            if confirmed_direction is None:
                continue
            await session.execute(
                text("""
                    UPDATE cointegration_results
                    SET granger_direction = :granger_direction
                    WHERE commodity_id = :commodity_id AND segment_id = :segment_id
                """),
                {
                    "granger_direction": confirmed_direction,
                    "commodity_id": cid,
                    "segment_id": seg,
                },
            )

        await session.commit()
    except DBError:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise DBError(
            "DB-TX-001",
            "Phase 5 트랜잭션 롤백 — granger_results 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    count = len(df)
    await append_phase_to_run(session, run_id, "5")
    logger.info("Phase 5 완료", extra={"run_id": run_id, "rows": count})
    return count
