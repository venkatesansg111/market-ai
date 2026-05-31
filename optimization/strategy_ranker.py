"""StrategyRanker — weighted composite scoring and ranking of optimization results."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from optimization.optimization_models import OptimizationResult, RankingScore


def _normalize(values: list[float], invert: bool = False) -> list[float]:
    """Min-max normalize *values*. Returns [0.5, …] when all values are equal."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5] * len(values)
    norm = [(v - min_v) / (max_v - min_v) for v in values]
    if invert:
        norm = [1.0 - n for n in norm]
    return norm


class StrategyRanker:
    """Ranks optimization results using a weighted composite score.

    Weight allocation:
        CAGR          25 %  (higher is better)
        Sharpe        20 %  (higher is better)
        Sortino       20 %  (higher is better)
        Profit factor 15 %  (higher is better)
        Win rate      10 %  (higher is better)
        Max drawdown  10 %  (lower is better — inverted)
    """

    WEIGHTS: dict[str, float] = {
        "cagr": 0.25,
        "sharpe": 0.20,
        "sortino": 0.20,
        "profit_factor": 0.15,
        "win_rate": 0.10,
        "max_drawdown": 0.10,
    }

    def rank(self, results: list[OptimizationResult]) -> list[RankingScore]:
        """Compute composite scores and return results sorted best → worst.

        Returns an empty list when *results* is empty.
        """
        if not results:
            return []

        cagr_vals = [r.cagr for r in results]
        sharpe_vals = [r.sharpe for r in results]
        sortino_vals = [r.sortino for r in results]
        pf_vals = [r.profit_factor for r in results]
        wr_vals = [r.win_rate for r in results]
        dd_vals = [r.max_drawdown for r in results]

        norm_cagr = _normalize(cagr_vals)
        norm_sharpe = _normalize(sharpe_vals)
        norm_sortino = _normalize(sortino_vals)
        norm_pf = _normalize(pf_vals)
        norm_wr = _normalize(wr_vals)
        norm_dd = _normalize(dd_vals, invert=True)  # lower drawdown → higher score

        w = self.WEIGHTS
        scored = []
        for i, r in enumerate(results):
            composite = (
                w["cagr"] * norm_cagr[i]
                + w["sharpe"] * norm_sharpe[i]
                + w["sortino"] * norm_sortino[i]
                + w["profit_factor"] * norm_pf[i]
                + w["win_rate"] * norm_wr[i]
                + w["max_drawdown"] * norm_dd[i]
            )
            scored.append((composite, r))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            RankingScore(
                rank=rank,
                strategy_name=r.strategy_name,
                parameters=dict(r.parameters),
                composite_score=round(score, 6),
                cagr=r.cagr,
                sharpe=r.sharpe,
                sortino=r.sortino,
                profit_factor=r.profit_factor,
                win_rate=r.win_rate,
                max_drawdown=r.max_drawdown,
            )
            for rank, (score, r) in enumerate(scored, start=1)
        ]

    def top_n(self, results: list[OptimizationResult], n: int = 5) -> list[RankingScore]:
        """Return the top *n* ranked results."""
        return self.rank(results)[:n]

    def worst_n(self, results: list[OptimizationResult], n: int = 5) -> list[RankingScore]:
        """Return the *n* worst-ranked results (ascending order)."""
        ranked = self.rank(results)
        return list(reversed(ranked))[:n]

    def stable_strategies(
        self,
        results: list[OptimizationResult],
        top_n: int = 5,
    ) -> list[RankingScore]:
        """Return strategies with the most consistent composite scores across parameters.

        Groups results by strategy name, computes the coefficient of variation
        (CV = std / mean) of composite scores within each group, and returns the
        best-parameter ranking for the strategies with the lowest CV.

        Strategies represented by a single result get CV = 0 (maximally stable).
        """
        if not results:
            return []

        groups: dict[str, list[OptimizationResult]] = defaultdict(list)
        for r in results:
            groups[r.strategy_name].append(r)

        stability_scores: list[tuple[float, RankingScore]] = []
        for strat_name, strat_results in groups.items():
            ranked = self.rank(strat_results)
            if not ranked:
                continue

            scores = [rs.composite_score for rs in ranked]
            mean = sum(scores) / len(scores)

            if len(scores) == 1 or mean == 0:
                cv = 0.0
            else:
                variance = sum((s - mean) ** 2 for s in scores) / len(scores)
                std = variance ** 0.5
                cv = std / mean

            stability_scores.append((cv, ranked[0]))

        stability_scores.sort(key=lambda x: x[0])
        return [rs for _, rs in stability_scores[:top_n]]
