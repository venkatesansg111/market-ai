"""AdaptiveLearningEngine — update scoring matrix from performance history."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Optional

from config import settings
from meta.meta_models import LearningState, RegimeType, StrategyPerformanceRecord
from meta.strategy_scoring import StrategyScorer
from meta.strategy_weights import StrategyWeightsManager
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)

# Blend factor: new_score = old * (1 - α) + perf_derived_score * α
_DEFAULT_LEARNING_RATE = 0.10
_MIN_TRADES_TO_LEARN = 5

# Score range for the derived score from performance composite
_SCORE_SCALE = 100.0


PersistFn = Callable[[LearningState], None]
LoadFn = Callable[[], Optional[LearningState]]


class AdaptiveLearningEngine:
    """Adjusts the :class:`StrategyScorer` scoring matrix based on observed performance.

    The engine blends the current score with a performance-derived target::

        new_score = old_score * (1 - lr) + target_score * lr

    where ``target_score = composite_score(perf_record) * 100``.

    A custom persist / load function can be injected for unit testing::

        engine = AdaptiveLearningEngine(
            scorer=scorer,
            persist_fn=lambda state: None,   # no-op
        )
    """

    def __init__(
        self,
        scorer: StrategyScorer,
        weights_manager: Optional[StrategyWeightsManager] = None,
        learning_rate: float = _DEFAULT_LEARNING_RATE,
        persist_fn: Optional[PersistFn] = None,
        load_fn: Optional[LoadFn] = None,
    ) -> None:
        self._scorer = scorer
        self._weights = weights_manager or StrategyWeightsManager()
        self._lr = learning_rate
        self._persist_fn = persist_fn or self._db_persist
        self._load_fn = load_fn or self._db_load
        self._state: LearningState = LearningState.empty()

    # ── Public API ────────────────────────────────────────────────────────

    def update(self, records: list[StrategyPerformanceRecord]) -> None:
        """Ingest performance records and update the scoring matrix.

        Records with fewer than :data:`_MIN_TRADES_TO_LEARN` trades are ignored
        to prevent noise from tiny sample sizes.

        After updating scores, the learning state is persisted.
        """
        if not records:
            return

        for rec in records:
            if rec.total_trades < _MIN_TRADES_TO_LEARN:
                logger.debug(
                    "[AdaptiveLearning] Skipping %s/%s — only %d trades",
                    rec.strategy_name, rec.regime_type.value, rec.total_trades,
                )
                continue
            self._update_one(rec)
            self._weights.record_performance(rec)

        self._state.last_updated = datetime.utcnow()
        self._state.version += 1
        self._persist_fn(self._state)

        logger.info(
            "[AdaptiveLearning] Updated %d records, state version=%d",
            len(records),
            self._state.version,
        )

    def load_state(self) -> LearningState:
        """Load persisted learning state and apply overrides to scorer."""
        loaded = self._load_fn()
        if loaded is not None:
            self._state = loaded
            self._scorer.apply_overrides(loaded.scoring_overrides)
            logger.info(
                "[AdaptiveLearning] Loaded state version=%d, updated=%s",
                loaded.version,
                loaded.last_updated.isoformat(),
            )
        return self._state

    def current_state(self) -> LearningState:
        """Return the in-memory learning state without loading from DB."""
        return self._state

    def reset(self) -> None:
        """Reset scoring overrides and learning state to baseline."""
        self._scorer.reset_to_baseline()
        self._state = LearningState.empty()
        self._weights.reset()

    # ── Private helpers ───────────────────────────────────────────────────

    def _update_one(self, rec: StrategyPerformanceRecord) -> None:
        """Blend existing score with performance-derived target for one record."""
        old_score = self._scorer.get_score(rec.strategy_name, rec.regime_type)
        target_score = rec.composite_score() * _SCORE_SCALE
        new_score = old_score * (1 - self._lr) + target_score * self._lr
        self._scorer.update_score(rec.strategy_name, rec.regime_type, new_score)

        # Persist override in state
        if rec.strategy_name not in self._state.scoring_overrides:
            self._state.scoring_overrides[rec.strategy_name] = {}
        self._state.scoring_overrides[rec.strategy_name][rec.regime_type.value] = new_score

        # Track rolling performance history
        key = f"{rec.strategy_name}:{rec.regime_type.value}"
        hist = self._state.performance_history.setdefault(key, [])
        hist.append(rec.composite_score())
        if len(hist) > 50:
            self._state.performance_history[key] = hist[-50:]

    # ── Default DB persistence stubs (replaced by inject in tests) ────────

    @staticmethod
    def _db_persist(state: LearningState) -> None:
        try:
            from database.connection import get_session
            from database.models_meta import LearningStateSnapshot
            payload = json.dumps({
                "scoring_overrides": state.scoring_overrides,
                "regime_weights": state.regime_weights,
                "performance_history": state.performance_history,
                "version": state.version,
            })
            with get_session() as session:
                session.add(
                    LearningStateSnapshot(
                        version=state.version,
                        payload=payload,
                        created_at=state.last_updated,
                    )
                )
                session.commit()
        except Exception as exc:
            logger.error("[AdaptiveLearning] Failed to persist state: %s", exc)

    @staticmethod
    def _db_load() -> Optional[LearningState]:
        try:
            from database.connection import get_session
            from database.models_meta import LearningStateSnapshot
            from sqlalchemy import select
            with get_session() as session:
                row = session.execute(
                    select(LearningStateSnapshot)
                    .order_by(LearningStateSnapshot.version.desc())
                    .limit(1)
                ).scalar_one_or_none()
            if row is None:
                return None
            data = json.loads(row.payload)
            return LearningState(
                scoring_overrides=data.get("scoring_overrides", {}),
                regime_weights=data.get("regime_weights", {}),
                performance_history=data.get("performance_history", {}),
                last_updated=row.created_at,
                version=data.get("version", 1),
            )
        except Exception as exc:
            logger.error("[AdaptiveLearning] Failed to load state: %s", exc)
            return None
