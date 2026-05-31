from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtesting.backtest_models import BacktestResult, Trade
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)


def _dec_to_str(v: Any) -> Any:
    """JSON-serializable conversion for Decimal and datetime."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


class BacktestReporter:
    """Generates backtest reports in JSON, CSV, and Markdown formats.

    Usage:
        reporter = BacktestReporter(result)
        reporter.save(Path("reports"))
        # Writes: reports/{run_name}.json, .csv, .md
    """

    def __init__(self, result: BacktestResult) -> None:
        self._r = result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, output_dir: Path = Path("reports")) -> dict[str, Path]:
        """Write all report formats. Returns dict of format → path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._r.run_name.replace(" ", "_").replace("/", "-")

        paths: dict[str, Path] = {}
        paths["json"] = self._write_json(output_dir / f"{safe_name}.json")
        paths["csv"] = self._write_csv(output_dir / f"{safe_name}_trades.csv")
        paths["md"] = self._write_markdown(output_dir / f"{safe_name}.md")

        for fmt, path in paths.items():
            logger.info("[Reporter] Saved %s report: %s", fmt.upper(), path)
        return paths

    def to_json(self) -> str:
        """Return JSON string of the full report."""
        return json.dumps(self._build_json_dict(), indent=2, default=_dec_to_str)

    def to_markdown(self) -> str:
        """Return Markdown string of the report."""
        return self._build_markdown()

    # ------------------------------------------------------------------
    # Format builders
    # ------------------------------------------------------------------

    def _build_json_dict(self) -> dict:
        r = self._r
        return {
            "run_name": r.run_name,
            "strategy_name": r.strategy_name,
            "instrument": r.instrument,
            "timeframe": r.timeframe,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "performance": {
                "starting_capital": _dec_to_str(r.starting_capital),
                "ending_capital": _dec_to_str(r.ending_capital),
                "total_return_pct": _dec_to_str(r.total_return_pct),
                "cagr_pct": _dec_to_str(r.cagr_pct),
                "max_drawdown_pct": _dec_to_str(r.max_drawdown_pct),
                "sharpe_ratio": _dec_to_str(r.sharpe_ratio),
                "sortino_ratio": _dec_to_str(r.sortino_ratio),
                "calmar_ratio": _dec_to_str(r.calmar_ratio),
                "recovery_factor": _dec_to_str(r.recovery_factor),
            },
            "trade_statistics": {
                "total_trades": r.total_trades,
                "winning_trades": r.winning_trades,
                "losing_trades": r.losing_trades,
                "win_rate_pct": _dec_to_str(r.win_rate_pct),
                "profit_factor": _dec_to_str(r.profit_factor),
                "expectancy": _dec_to_str(r.expectancy),
                "avg_winner": _dec_to_str(r.avg_winner),
                "avg_loser": _dec_to_str(r.avg_loser),
                "avg_holding_minutes": _dec_to_str(r.avg_holding_minutes),
                "longest_win_streak": r.longest_win_streak,
                "longest_loss_streak": r.longest_loss_streak,
            },
            "monthly_returns": r.monthly_returns,
            "yearly_returns": r.yearly_returns,
            "trades": [self._trade_to_dict(t) for t in r.trades],
            "equity_curve_sample": [
                {
                    "time": ep.snapshot_time.isoformat(),
                    "equity": float(ep.equity),
                    "drawdown_pct": float(ep.drawdown_pct),
                }
                for ep in r.equity_curve[::max(1, len(r.equity_curve) // 100)]
            ],
        }

    def _write_json(self, path: Path) -> Path:
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def _write_csv(self, path: Path) -> Path:
        if not self._r.trades:
            path.write_text("No trades.\n", encoding="utf-8")
            return path

        fieldnames = [
            "trade_id", "instrument", "side",
            "entry_time", "exit_time", "holding_minutes",
            "entry_price", "exit_price",
            "quantity", "gross_pnl", "net_pnl",
            "commission", "slippage", "return_pct",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in self._r.trades:
                writer.writerow({
                    "trade_id": t.trade_id,
                    "instrument": t.instrument,
                    "side": t.side.value,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "holding_minutes": t.holding_minutes,
                    "entry_price": float(t.entry_price),
                    "exit_price": float(t.exit_price),
                    "quantity": t.quantity,
                    "gross_pnl": float(t.gross_pnl),
                    "net_pnl": float(t.net_pnl),
                    "commission": float(t.commission),
                    "slippage": float(t.slippage),
                    "return_pct": float(t.return_pct),
                })
        return path

    def _write_markdown(self, path: Path) -> Path:
        path.write_text(self._build_markdown(), encoding="utf-8")
        return path

    def _build_markdown(self) -> str:
        r = self._r
        lines: list[str] = []

        lines += [
            f"# Backtest Report: {r.run_name}", "",
            "## Configuration", "",
            "| Parameter | Value |",
            "|---|---|",
            f"| Strategy | {r.strategy_name} |",
            f"| Instrument | {r.instrument} |",
            f"| Timeframe | {r.timeframe} |",
            f"| Start Date | {r.start_date.date()} |",
            f"| End Date | {r.end_date.date()} |",
            f"| Starting Capital | ₹{float(r.starting_capital):,.2f} |",
            "",
        ]

        lines += [
            "## Performance Summary", "",
            "| Metric | Value |",
            "|---|---|",
            f"| Ending Capital | ₹{float(r.ending_capital):,.2f} |",
            f"| Total Return | {float(r.total_return_pct):.2f}% |",
            f"| CAGR | {float(r.cagr_pct):.2f}% |",
            f"| Max Drawdown | {float(r.max_drawdown_pct):.2f}% |",
            f"| Sharpe Ratio | {float(r.sharpe_ratio):.4f} |",
            f"| Sortino Ratio | {float(r.sortino_ratio):.4f} |",
            f"| Calmar Ratio | {float(r.calmar_ratio):.4f} |",
            f"| Recovery Factor | {float(r.recovery_factor):.4f} |",
            "",
        ]

        lines += [
            "## Trade Statistics", "",
            "| Metric | Value |",
            "|---|---|",
            f"| Total Trades | {r.total_trades} |",
            f"| Winning Trades | {r.winning_trades} |",
            f"| Losing Trades | {r.losing_trades} |",
            f"| Win Rate | {float(r.win_rate_pct):.2f}% |",
            f"| Profit Factor | {float(r.profit_factor):.4f} |",
            f"| Expectancy | ₹{float(r.expectancy):.2f} |",
            f"| Avg Winner | ₹{float(r.avg_winner):,.2f} |",
            f"| Avg Loser | ₹{float(r.avg_loser):,.2f} |",
            f"| Avg Holding | {float(r.avg_holding_minutes):.0f} min |",
            f"| Longest Win Streak | {r.longest_win_streak} |",
            f"| Longest Loss Streak | {r.longest_loss_streak} |",
            "",
        ]

        if r.yearly_returns:
            lines += ["## Yearly Returns", "", "| Year | Return |", "|---|---|"]
            for yr, ret in sorted(r.yearly_returns.items()):
                sign = "+" if ret >= 0 else ""
                lines.append(f"| {yr} | {sign}{ret:.2f}% |")
            lines.append("")

        if r.monthly_returns:
            lines += ["## Monthly Returns", "", "| Month | Return |", "|---|---|"]
            for mo, ret in sorted(r.monthly_returns.items()):
                sign = "+" if ret >= 0 else ""
                lines.append(f"| {mo} | {sign}{ret:.2f}% |")
            lines.append("")

        top_winners = sorted(r.trades, key=lambda t: t.net_pnl, reverse=True)[:5]
        if top_winners:
            lines += ["## Top 5 Winners", "", "| Entry | Exit | Net PnL | Return |", "|---|---|---|---|"]
            for t in top_winners:
                lines.append(
                    f"| {t.entry_time.date()} | {t.exit_time.date()} "
                    f"| ₹{float(t.net_pnl):,.2f} | {float(t.return_pct):.2f}% |"
                )
            lines.append("")

        top_losers = sorted(r.trades, key=lambda t: t.net_pnl)[:5]
        if top_losers:
            lines += ["## Top 5 Losers", "", "| Entry | Exit | Net PnL | Return |", "|---|---|---|---|"]
            for t in top_losers:
                lines.append(
                    f"| {t.entry_time.date()} | {t.exit_time.date()} "
                    f"| ₹{float(t.net_pnl):,.2f} | {float(t.return_pct):.2f}% |"
                )
            lines.append("")

        lines += [
            "---",
            f"*Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        ]

        return "\n".join(lines)

    @staticmethod
    def _trade_to_dict(t: Trade) -> dict:
        return {
            "trade_id": t.trade_id,
            "instrument": t.instrument,
            "side": t.side.value,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat(),
            "holding_minutes": t.holding_minutes,
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price),
            "quantity": t.quantity,
            "gross_pnl": float(t.gross_pnl),
            "net_pnl": float(t.net_pnl),
            "commission": float(t.commission),
            "slippage": float(t.slippage),
            "return_pct": float(t.return_pct),
            "is_winner": t.is_winner,
        }
