"""Phase 4 — model_params / irf_data / baselines 적재

feature_spec_DB-PIPELINE_v2 §2 입력 데이터 기준.
exception_design_v3 §2 에러 체이닝 패턴 준수.

JSON 필드명 매핑:
  segment                  → segment_id
  lag_selection_criterion  → lag_criterion
  estimation_period_start  → estimation_start  (YYYY-MM → DATE)
  estimation_period_end    → estimation_end    (YYYY-MM → DATE)

subperiod_id: Phase 6 완료 전에는 NULL (전체 기간만 적재).
NULL subperiod_id UPSERT: ON CONFLICT 미지원 → DELETE + INSERT.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.loader.base import (
    _v,
    append_phase_to_run,
    normalize_yyyymm_to_date,
    validate_period_day,
)

logger = logging.getLogger(__name__)

_PHASE4_ROOT = Path(settings.pipeline_data_root) / "phase4"


async def _upsert_model_params(
    session: AsyncSession,
    run_id: int,
) -> int:
    """model_params/{cid}_{seg}_model.json → model_params UPSERT (subperiod_id=NULL)."""
    pattern = _PHASE4_ROOT / "model_params"
    files = sorted(pattern.glob("*_model.json")) if pattern.exists() else []
    count = 0

    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))

        cid = str(data["commodity_id"])
        seg = str(data.get("segment", data.get("segment_id", "")))
        estimation_start: date | None = None
        estimation_end: date | None = None

        raw_start = data.get("estimation_period_start")
        raw_end = data.get("estimation_period_end")
        if raw_start:
            estimation_start = normalize_yyyymm_to_date(str(raw_start))
            validate_period_day(estimation_start, "model_params")
        if raw_end:
            estimation_end = normalize_yyyymm_to_date(str(raw_end))
            validate_period_day(estimation_end, "model_params")

        # NULL subperiod_id — PostgreSQL UNIQUE treats NULLs as distinct;
        # DELETE + INSERT 로 멱등 UPSERT 구현
        await session.execute(
            text("""
                DELETE FROM model_params
                WHERE commodity_id = :cid AND segment_id = :seg AND subperiod_id IS NULL
            """),
            {"cid": cid, "seg": seg},
        )

        await session.execute(
            text("""
                INSERT INTO model_params (
                    commodity_id, segment_id, subperiod_id,
                    model_type, lag_selected, lag_criterion, n_obs,
                    estimation_start, estimation_end, cointegrated,
                    det_order, coint_rank, aic, bic, log_likelihood,
                    pipeline_run_id
                ) VALUES (
                    :commodity_id, :segment_id, NULL,
                    :model_type, :lag_selected, :lag_criterion, :n_obs,
                    :estimation_start, :estimation_end, :cointegrated,
                    :det_order, :coint_rank, :aic, :bic, :log_likelihood,
                    :pipeline_run_id
                )
            """),
            {
                "commodity_id": cid,
                "segment_id": seg,
                "model_type": str(data["model_type"]),
                "lag_selected": int(data["lag_selected"]),
                "lag_criterion": str(data.get("lag_selection_criterion", "AIC")),
                "n_obs": int(data["n_obs"]),
                "estimation_start": estimation_start,
                "estimation_end": estimation_end,
                "cointegrated": bool(data.get("cointegrated", False)),
                "det_order": _v(data.get("det_order")),
                "coint_rank": _v(data.get("coint_rank")),
                "aic": _v(data.get("aic")),
                "bic": _v(data.get("bic")),
                "log_likelihood": _v(data.get("log_likelihood")),
                "pipeline_run_id": run_id,
            },
        )
        count += 1

    return count


async def _upsert_irf_data(
    session: AsyncSession,
    run_id: int,
) -> int:
    """irf/{cid}_{seg}_irf.csv → irf_data UPSERT (subperiod_id=NULL).

    horizon=0 행에만 peak 컬럼 저장, 나머지 행은 NULL.
    """
    pattern = _PHASE4_ROOT / "irf"
    files = sorted(pattern.glob("*_irf.csv")) if pattern.exists() else []
    count = 0

    for fp in files:
        # 파일명에서 commodity_id, segment_id 파싱: {cid}_{seg}_irf.csv
        stem = fp.stem  # e.g. "wheat_A_irf", "wheat_D_prime_irf"
        # commodity_id 에는 언더스코어 없음 → 첫 번째 '_' 로 cid 분리
        base = stem[: stem.rfind("_irf")]   # "wheat_A" | "wheat_D_prime"
        first_us = base.index("_")
        cid = base[:first_us]
        seg = base[first_us + 1:]           # "A" | "D_prime"

        df = pd.read_csv(fp)

        # NULL subperiod_id — DELETE + INSERT
        await session.execute(
            text("""
                DELETE FROM irf_data
                WHERE commodity_id = :cid AND segment_id = :seg AND subperiod_id IS NULL
            """),
            {"cid": cid, "seg": seg},
        )

        for _, row in df.iterrows():
            h = int(row["horizon"])
            await session.execute(
                text("""
                    INSERT INTO irf_data (
                        commodity_id, segment_id, subperiod_id, horizon,
                        irf_downstream, irf_lower_ci, irf_upper_ci,
                        irf_peak_horizon, irf_peak_magnitude,
                        pipeline_run_id
                    ) VALUES (
                        :commodity_id, :segment_id, NULL, :horizon,
                        :irf_downstream, :irf_lower_ci, :irf_upper_ci,
                        :irf_peak_horizon, :irf_peak_magnitude,
                        :pipeline_run_id
                    )
                """),
                {
                    "commodity_id": cid,
                    "segment_id": seg,
                    "horizon": h,
                    "irf_downstream": float(row["irf_downstream"]),
                    "irf_lower_ci": _v(row.get("irf_lower_ci")),
                    "irf_upper_ci": _v(row.get("irf_upper_ci")),
                    # peak 컬럼: horizon=0 행에만 저장 (db_schema_v5 §irf_data)
                    "irf_peak_horizon": int(row["irf_peak_horizon"]) if h == 0 and not pd.isna(row.get("irf_peak_horizon", float("nan"))) else None,
                    "irf_peak_magnitude": float(row["irf_peak_magnitude"]) if h == 0 and not pd.isna(row.get("irf_peak_magnitude", float("nan"))) else None,
                    "pipeline_run_id": run_id,
                },
            )
            count += 1

    return count


async def _upsert_baselines(
    session: AsyncSession,
    run_id: int,
) -> int:
    """baseline/{cid}_{seg}_baseline.json → baselines UPSERT (subperiod_id=NULL)."""
    pattern = _PHASE4_ROOT / "baseline"
    files = sorted(pattern.glob("*_baseline.json")) if pattern.exists() else []
    count = 0

    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))

        cid = str(data["commodity_id"])
        seg = str(data.get("segment", data.get("segment_id", "")))

        raw_start = data.get("estimation_period_start")
        raw_end = data.get("estimation_period_end")
        raw_warmup = data.get("warmup_end")

        estimation_start = normalize_yyyymm_to_date(str(raw_start)) if raw_start else None
        estimation_end = normalize_yyyymm_to_date(str(raw_end)) if raw_end else None
        warmup_end = normalize_yyyymm_to_date(str(raw_warmup)) if raw_warmup else None

        if estimation_start:
            validate_period_day(estimation_start, "baselines")
        if estimation_end:
            validate_period_day(estimation_end, "baselines")
        if warmup_end:
            validate_period_day(warmup_end, "baselines")

        # NULL subperiod_id — DELETE + INSERT
        await session.execute(
            text("""
                DELETE FROM baselines
                WHERE commodity_id = :cid AND segment_id = :seg AND subperiod_id IS NULL
            """),
            {"cid": cid, "seg": seg},
        )

        await session.execute(
            text("""
                INSERT INTO baselines (
                    commodity_id, segment_id, subperiod_id,
                    normal_transmission_lag, transmission_elasticity,
                    warmup_end, model_type, estimation_start, estimation_end,
                    n_obs, pipeline_run_id
                ) VALUES (
                    :commodity_id, :segment_id, NULL,
                    :normal_transmission_lag, :transmission_elasticity,
                    :warmup_end, :model_type, :estimation_start, :estimation_end,
                    :n_obs, :pipeline_run_id
                )
            """),
            {
                "commodity_id": cid,
                "segment_id": seg,
                "normal_transmission_lag": int(data["normal_transmission_lag"]),
                "transmission_elasticity": float(data["transmission_elasticity"]),
                "warmup_end": warmup_end,
                "model_type": str(data["model_type"]),
                "estimation_start": estimation_start,
                "estimation_end": estimation_end,
                "n_obs": int(data["n_obs"]),
                "pipeline_run_id": run_id,
            },
        )
        count += 1

    return count


async def load_phase4(
    session: AsyncSession,
    run_id: int,
) -> dict[str, int]:
    """Phase 4 단일 트랜잭션 — model_params, irf_data, baselines 적재.

    Returns dict with row counts per table.
    """
    try:
        mp_count = await _upsert_model_params(session, run_id)
        irf_count = await _upsert_irf_data(session, run_id)
        bl_count = await _upsert_baselines(session, run_id)
        await session.commit()
    except DBError:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise DBError(
            "DB-TX-001",
            "Phase 4 트랜잭션 롤백 — model_params/irf_data/baselines 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    await append_phase_to_run(session, run_id, "4")
    logger.info(
        "Phase 4 완료",
        extra={"run_id": run_id, "model_params": mp_count, "irf_data": irf_count, "baselines": bl_count},
    )
    return {"model_params": mp_count, "irf_data": irf_count, "baselines": bl_count}
