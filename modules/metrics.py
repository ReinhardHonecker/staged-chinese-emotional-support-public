from __future__ import annotations

import sqlite3
from datetime import datetime

from config import METRICS_DB_PATH, METRICS_ENABLED
from modules.models import PipelineResult


def record_pipeline_metric(result: PipelineResult) -> None:
    if not METRICS_ENABLED:
        return
    METRICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(METRICS_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_metrics (
                created_at TEXT NOT NULL,
                stage TEXT NOT NULL,
                intent TEXT NOT NULL,
                emotion TEXT NOT NULL,
                safety_status TEXT NOT NULL,
                strategy TEXT NOT NULL,
                used_fallback INTEGER NOT NULL,
                latency_ms INTEGER NOT NULL,
                guard_passed INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO pipeline_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                result.plan.stage.value,
                result.analysis.user_intent.value,
                result.analysis.primary_emotion.value,
                result.analysis.safety.status.value,
                result.plan.primary_strategy,
                int(result.used_fallback),
                result.latency_ms,
                int(result.audit.safety_passed and result.audit.stage_adherence),
            ),
        )
