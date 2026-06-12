"""Phase 3 — cointegration_results 적재.

컬럼명 매핑:
  segment / upstream / downstream / model_selected → segment_id / upstream_col / downstream_col / model_type
  trace_stat_r0 / eigen_stat_r0 → trace_stat / maxeig_stat (pvalue Johansen 미제공 → NULL)

DB 전용 컬럼: upstream/downstream_integration_order (stationarity_results 조회),
  integration_order_match, coint_tested, coint_rank, granger_direction (Phase 5 UPDATE)
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


async def _fetch_integration_orders(session: AsyncSession) -> dict[tuple[str, str], int]:
    result = await session.execute(
        text("SELECT commodity_id, price_col, integration_order FROM stationarity_results")
    )
    return {(row.commodity_id, row.price_col): row.integration_order for row in result}


async def load_cointegration_results(
    session: AsyncSession,
    run_id: int,
) -> int:
    """cointegration_results.csv → cointegration_results UPSERT."""
    csv_path = Path(settings.pipeline_data_root) / "phase3" / "cointegration_results.csv"
    if not csv_path.exists():
        raise DBError(
            "DB-TX-001",
            f"Phase 3 입력 파일 없음: {csv_path}",
            {"path": str(csv_path), "run_id": run_id},
        )

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        logger.warning("Phase 3 cointegration_results.csv 비어있음 — 적재 건너뜀", extra={"run_id": run_id})
        return 0
    except Exception as e:
        raise DBError(
            "DB-TX-001",
            f"Phase 3 CSV 읽기 실패: {csv_path}",
            {"path": str(csv_path), "run_id": run_id, "error": str(e)},
        ) from e

    if df.empty:
        logger.warning("Phase 3 cointegration_results.csv 유효 데이터 없음 — 적재 건너뜀", extra={"run_id": run_id})
        return 0

    int_orders = await _fetch_integration_orders(session)

    try:
        for _, row in df.iterrows():
            cid = str(row["commodity_id"])
            seg = str(row["segment"])
            upstream = str(row["upstream"])
            downstream = str(row["downstream"])

            upstream_io = int_orders.get((cid, upstream))
            downstream_io = int_orders.get((cid, downstream))

            integration_order_match = (
                (upstream_io == downstream_io)
                if upstream_io is not None and downstream_io is not None
                else None
            )
            coint_tested = bool(upstream_io == 1 and downstream_io == 1)

            cointegrated_val = _v(row.get("cointegrated"))
            if isinstance(cointegrated_val, str):
                cointegrated_val = cointegrated_val.lower() == "true"

            coint_rank = 1 if cointegrated_val else 0

            integration_flag_raw = row.get("integration_flag")
            i2_flag = not (pd.isna(integration_flag_raw) if integration_flag_raw is not None else True)

            model_type_raw = _v(row.get("model_selected"))

            await session.execute(
                text("""
                    INSERT INTO cointegration_results (
                        commodity_id, segment_id, upstream_col, downstream_col,
                        upstream_integration_order, downstream_integration_order,
                        integration_order_match, coint_tested,
                        trace_stat, trace_pvalue, maxeig_stat, maxeig_pvalue,
                        coint_rank, cointegrated, i2_flag, model_type,
                        granger_direction, pipeline_run_id
                    ) VALUES (
                        :commodity_id, :segment_id, :upstream_col, :downstream_col,
                        :upstream_integration_order, :downstream_integration_order,
                        :integration_order_match, :coint_tested,
                        :trace_stat, :trace_pvalue, :maxeig_stat, :maxeig_pvalue,
                        :coint_rank, :cointegrated, :i2_flag, :model_type,
                        :granger_direction, :pipeline_run_id
                    )
                    ON CONFLICT (commodity_id, segment_id) DO UPDATE SET
                        upstream_col = EXCLUDED.upstream_col,
                        downstream_col = EXCLUDED.downstream_col,
                        upstream_integration_order = EXCLUDED.upstream_integration_order,
                        downstream_integration_order = EXCLUDED.downstream_integration_order,
                        integration_order_match = EXCLUDED.integration_order_match,
                        coint_tested = EXCLUDED.coint_tested,
                        trace_stat = EXCLUDED.trace_stat,
                        trace_pvalue = EXCLUDED.trace_pvalue,
                        maxeig_stat = EXCLUDED.maxeig_stat,
                        maxeig_pvalue = EXCLUDED.maxeig_pvalue,
                        coint_rank = EXCLUDED.coint_rank,
                        cointegrated = EXCLUDED.cointegrated,
                        i2_flag = EXCLUDED.i2_flag,
                        model_type = EXCLUDED.model_type,
                        pipeline_run_id = EXCLUDED.pipeline_run_id
                """),
                {
                    "commodity_id": cid,
                    "segment_id": seg,
                    "upstream_col": upstream,
                    "downstream_col": downstream,
                    "upstream_integration_order": upstream_io,
                    "downstream_integration_order": downstream_io,
                    "integration_order_match": integration_order_match,
                    "coint_tested": coint_tested,
                    "trace_stat": _v(row.get("trace_stat_r0")),
                    "trace_pvalue": None,
                    "maxeig_stat": _v(row.get("eigen_stat_r0")),
                    "maxeig_pvalue": None,
                    "coint_rank": coint_rank,
                    "cointegrated": cointegrated_val,
                    "i2_flag": i2_flag,
                    "model_type": model_type_raw,
                    "granger_direction": None,
                    "pipeline_run_id": run_id,
                },
            )
        await session.commit()
    except Exception as e:
        await session.rollback()
        if isinstance(e, DBError):
            raise
        raise DBError(
            "DB-TX-001",
            "Phase 3 트랜잭션 롤백 — cointegration_results 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    count = len(df)
    await append_phase_to_run(session, run_id, "3")
    logger.info("Phase 3 완료", extra={"run_id": run_id, "rows": count})
    return count
