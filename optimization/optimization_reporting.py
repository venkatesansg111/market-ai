"""OptimizationReporter — generate JSON, CSV, and Markdown research reports."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from optimization.optimization_models import (
    OptimizationResult,
    RankingScore,
    RegimeResult,
    ResearchReport,
)


def _default_serializer(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _result_to_dict(r: OptimizationResult) -> dict:
    return {
        "run_id": r.run_id,
        "strategy_name": r.strategy_name,
        "instrument": r.instrument,
        "timeframe": r.timeframe,
        "parameters": r.parameters,
        "train_start": r.train_start.isoformat() if r.train_start else None,
        "train_end": r.train_end.isoformat() if r.train_end else None,
        "test_start": r.test_start.isoformat(),
        "test_end": r.test_end.isoformat(),
        "cagr": r.cagr,
        "sharpe": r.sharpe,
        "sortino": r.sortino,
        "max_drawdown": r.max_drawdown,
        "profit_factor": r.profit_factor,
        "win_rate": r.win_rate,
        "expectancy": r.expectancy,
        "total_trades": r.total_trades,
        "created_at": r.created_at.isoformat(),
    }


def _ranking_to_dict(rs: RankingScore) -> dict:
    return {
        "rank": rs.rank,
        "strategy_name": rs.strategy_name,
        "parameters": rs.parameters,
        "composite_score": rs.composite_score,
        "cagr": rs.cagr,
        "sharpe": rs.sharpe,
        "sortino": rs.sortino,
        "profit_factor": rs.profit_factor,
        "win_rate": rs.win_rate,
        "max_drawdown": rs.max_drawdown,
    }


def _regime_to_dict(rr: RegimeResult) -> dict:
    return {
        "strategy_name": rr.strategy_name,
        "instrument": rr.instrument,
        "timeframe": rr.timeframe,
        "regime": rr.regime,
        "period_start": rr.period_start.isoformat(),
        "period_end": rr.period_end.isoformat(),
        "cagr": rr.cagr,
        "sharpe": rr.sharpe,
        "win_rate": rr.win_rate,
        "total_trades": rr.total_trades,
    }


class OptimizationReporter:
    """Generates research reports in JSON, CSV, and Markdown formats."""

    def save_all(self, report: ResearchReport, output_dir: Path) -> dict[str, Path]:
        """Save the complete research report to *output_dir* in all three formats.

        Returns a dict mapping format keys to file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = report.generated_at.strftime("%Y%m%d_%H%M%S")

        paths: dict[str, Path] = {}
        paths["json"] = self._save_json(report, output_dir / f"research_{ts}.json")
        paths["csv"] = self._save_csv(report.optimization_results, output_dir / f"research_{ts}_results.csv")
        paths["markdown"] = self._save_markdown(report, output_dir / f"research_{ts}.md")
        return paths

    # ------------------------------------------------------------------
    # Format writers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_json(report: ResearchReport, path: Path) -> Path:
        payload = {
            "title": report.title,
            "generated_at": report.generated_at.isoformat(),
            "instrument": report.instrument,
            "timeframe": report.timeframe,
            "analysis_start": report.analysis_start.isoformat(),
            "analysis_end": report.analysis_end.isoformat(),
            "strategy_rankings": [_ranking_to_dict(rs) for rs in report.strategy_rankings],
            "regime_results": [_regime_to_dict(rr) for rr in report.regime_results],
            "optimization_results": [_result_to_dict(r) for r in report.optimization_results],
            "walk_forward_results": [_result_to_dict(r) for r in report.walk_forward_results],
            "parameter_winners": report.parameter_winners,
            "summary": report.summary,
        }
        path.write_text(json.dumps(payload, indent=2, default=_default_serializer), encoding="utf-8")
        return path

    @staticmethod
    def _save_csv(results: list[OptimizationResult], path: Path) -> Path:
        if not results:
            path.write_text("", encoding="utf-8")
            return path

        fieldnames = [
            "run_id", "strategy_name", "instrument", "timeframe",
            "parameters", "test_start", "test_end",
            "cagr", "sharpe", "sortino", "max_drawdown",
            "profit_factor", "win_rate", "expectancy", "total_trades",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in results:
                row = _result_to_dict(r)
                row["parameters"] = json.dumps(r.parameters)
                writer.writerow(row)
        return path

    @staticmethod
    def _save_markdown(report: ResearchReport, path: Path) -> Path:
        lines: list[str] = [
            f"# {report.title}",
            f"",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Instrument:** {report.instrument} | **Timeframe:** {report.timeframe}",
            f"**Period:** {report.analysis_start.date()} → {report.analysis_end.date()}",
            "",
            "---",
            "",
            "## Strategy Rankings",
            "",
        ]

        if report.strategy_rankings:
            lines += [
                "| Rank | Strategy | Params | Score | CAGR% | Sharpe | Sortino | Win Rate% | DD% |",
                "|------|----------|--------|-------|-------|--------|---------|-----------|-----|",
            ]
            for rs in report.strategy_rankings[:10]:
                params_str = json.dumps(rs.parameters) if rs.parameters else "{}"
                lines.append(
                    f"| {rs.rank} | {rs.strategy_name} | `{params_str}` "
                    f"| {rs.composite_score:.3f} | {rs.cagr:.1f} | {rs.sharpe:.2f} "
                    f"| {rs.sortino:.2f} | {rs.win_rate:.1f} | {rs.max_drawdown:.1f} |"
                )
        else:
            lines.append("_No ranking data available._")

        lines += ["", "---", "", "## Market Regime Analysis", ""]

        if report.regime_results:
            lines += [
                "| Strategy | Regime | Period | CAGR% | Sharpe | Win Rate% | Trades |",
                "|----------|--------|--------|-------|--------|-----------|--------|",
            ]
            for rr in report.regime_results:
                period = f"{rr.period_start.date()} → {rr.period_end.date()}"
                lines.append(
                    f"| {rr.strategy_name} | {rr.regime} | {period} "
                    f"| {rr.cagr:.1f} | {rr.sharpe:.2f} | {rr.win_rate:.1f} | {rr.total_trades} |"
                )
        else:
            lines.append("_No regime data available._")

        lines += ["", "---", "", "## Parameter Winners", ""]
        if report.parameter_winners:
            for strat, params in report.parameter_winners.items():
                lines.append(f"**{strat}**: `{json.dumps(params)}`  ")
        else:
            lines.append("_No parameter winner data available._")

        lines += ["", "---", "", "## Summary", ""]
        for k, v in report.summary.items():
            lines.append(f"- **{k}**: {v}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
