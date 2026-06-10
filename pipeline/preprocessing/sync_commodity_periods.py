"""product_config.json → commodities.analysis_start/end DB 반영."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


async def sync_commodity_periods() -> int:
    config_path = Path(settings.pipeline_data_root) / "product_config.json"
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"product_config.json 없음: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    updated = 0
    async with AsyncSessionLocal() as session:
        for cid, cfg in config.items():
            start_s = cfg.get("common_start")
            end_s = cfg.get("common_end")
            if not start_s or not end_s:
                continue
            y1, m1 = (int(x) for x in start_s.split("-"))
            y2, m2 = (int(x) for x in end_s.split("-"))
            await session.execute(
                text(
                    """
                    UPDATE commodities
                    SET analysis_start = :start_d,
                        analysis_end   = :end_d,
                        updated_at     = NOW()
                    WHERE commodity_id = :cid
                    """
                ),
                {
                    "cid": cid,
                    "start_d": date(y1, m1, 1),
                    "end_d": date(y2, m2, 1),
                },
            )
            updated += 1
        await session.commit()
    return updated


def main() -> None:
    n = asyncio.run(sync_commodity_periods())
    print(f"commodities.analysis_start/end 갱신: {n}개 품목")


if __name__ == "__main__":
    main()
