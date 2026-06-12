"""Phase 2 — stationarity_results 적재."""
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


async def load_stationarity_results(
    session: AsyncSession,
    run_id: int,
) -> int:
    """stationarity_results.csv → stationarity_results UPSERT."""
    csv_path = Path(settings.pipeline_data_root) / "phase2" / "stationarity_results.csv"
    if not csv_path.exists():
        raise DBError(
            "DB-TX-001",
            f"Phase 2 입력 파일 없음: {csv_path}",
            {"path": str(csv_path), "run_id": run_id},
        )

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        logger.warning("Phase 2 stationarity_results.csv 비어있음 — 적재 건너뜀", extra={"run_id": run_id})
        return 0
    except Exception as e:
        raise DBError(
            "DB-TX-001",
            f"Phase 2 CSV 읽기 실패: {csv_path}",
            {"path": str(csv_path), "run_id": run_id, "error": str(e)},
        ) from e

    if df.empty or "integration_order" not in df.columns:
        logger.warning("Phase 2 stationarity_results.csv 유효 데이터 없음 — 적재 건너뜀", extra={"run_id": run_id})
        return 0

    # integration_order == 2 파생
    if "i2_flag" not in df.columns:
        df["i2_flag"] = df["integration_order"] == 2

    try:
        for _, row in df.iterrows():
            await session.execute(
                text("""
                    INSERT INTO stationarity_results (
                        commodity_id, price_col, n_obs,
                        level_adf_stat, level_adf_pvalue, level_adf_lags, level_adf_stationary,
                        level_kpss_stat, level_kpss_pvalue, level_kpss_stationary,
                        level_judgment, level_conflict_note,
                        diff_adf_stat, diff_adf_pvalue, diff_kpss_stat, diff_kpss_pvalue,
                        diff_judgment, integration_order, i2_flag, pipeline_run_id
                    ) VALUES (
                        :commodity_id, :price_col, :n_obs,
                        :level_adf_stat, :level_adf_pvalue, :level_adf_lags, :level_adf_stationary,
                        :level_kpss_stat, :level_kpss_pvalue, :level_kpss_stationary,
                        :level_judgment, :level_conflict_note,
                        :diff_adf_stat, :diff_adf_pvalue, :diff_kpss_stat, :diff_kpss_pvalue,
                        :diff_judgment, :integration_order, :i2_flag, :pipeline_run_id
                    )
                    ON CONFLICT (commodity_id, price_col) DO UPDATE SET
                        n_obs = EXCLUDED.n_obs,
                        level_adf_stat = EXCLUDED.level_adf_stat,
                        level_adf_pvalue = EXCLUDED.level_adf_pvalue,
                        level_adf_lags = EXCLUDED.level_adf_lags,
                        level_adf_stationary = EXCLUDED.level_adf_stationary,
                        level_kpss_stat = EXCLUDED.level_kpss_stat,
                        level_kpss_pvalue = EXCLUDED.level_kpss_pvalue,
                        level_kpss_stationary = EXCLUDED.level_kpss_stationary,
                        level_judgment = EXCLUDED.level_judgment,
                        level_conflict_note = EXCLUDED.level_conflict_note,
                        diff_adf_stat = EXCLUDED.diff_adf_stat,
                        diff_adf_pvalue = EXCLUDED.diff_adf_pvalue,
                        diff_kpss_stat = EXCLUDED.diff_kpss_stat,
                        diff_kpss_pvalue = EXCLUDED.diff_kpss_pvalue,
                        diff_judgment = EXCLUDED.diff_judgment,
                        integration_order = EXCLUDED.integration_order,
                        i2_flag = EXCLUDED.i2_flag,
                        pipeline_run_id = EXCLUDED.pipeline_run_id
                """),
                {
                    "commodity_id": str(row["commodity_id"]),
                    "price_col": str(row["column"]),
                    "n_obs": int(row["n_obs"]),
                    "level_adf_stat": _v(row.get("level_adf_stat")),
                    "level_adf_pvalue": _v(row.get("level_adf_pvalue")),
                    "level_adf_lags": None if pd.isna(row.get("level_adf_lags", float("nan"))) else int(row["level_adf_lags"]),
                    "level_adf_stationary": _v(row.get("level_adf_stationary")),
                    "level_kpss_stat": _v(row.get("level_kpss_stat")),
                    "level_kpss_pvalue": _v(row.get("level_kpss_pvalue")),
                    "level_kpss_stationary": _v(row.get("level_kpss_stationary")),
                    "level_judgment": _v(row.get("level_judgment")),
                    "level_conflict_note": _v(row.get("level_conflict_note")),
                    "diff_adf_stat": _v(row.get("diff_adf_stat")),
                    "diff_adf_pvalue": _v(row.get("diff_adf_pvalue")),
                    "diff_kpss_stat": _v(row.get("diff_kpss_stat")),
                    "diff_kpss_pvalue": _v(row.get("diff_kpss_pvalue")),
                    "diff_judgment": _v(row.get("diff_judgment")),
                    "integration_order": int(row["integration_order"]),
                    "i2_flag": bool(row["i2_flag"]),
                    "pipeline_run_id": run_id,
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
            "Phase 2 트랜잭션 롤백 — stationarity_results 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    count = len(df)
    await append_phase_to_run(session, run_id, "2")
    logger.info("Phase 2 완료", extra={"run_id": run_id, "rows": count})
    return count
