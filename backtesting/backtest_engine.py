from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from datetime import timedelta

from backtesting.backtest_models import BacktestConfig, BacktestResult, Trade, TradeAction
from backtesting.performance import PerformanceEngine
from backtesting.portfolio import Portfolio
from backtesting.risk_engine import RiskEngine
from backtesting.strategy_base import Strategy
from backtesting.strategy_signal_adapter import SignalToTradeAdapter
from backtesting.trade_executor import TradeExecutor
from config import settings
from database.connection import get_session
from database.models import MarketCandle, MarketIndicator
from database.models_backtesting import (
    BacktestRun,
    BacktestTrade,
    PortfolioSnapshot,
    create_backtest_tables,
)
from indicators.indicator_models import IndicatorRecord
from utils.logger import get_logger
from utils.time_utils import history_start_date

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ZERO = Decimal("0")


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        f = float(v)
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return Decimal(str(round(f, 8)))
    except (TypeError, ValueError):
        return None


class BacktestEngine:
    """Core orchestrator for the backtesting framework.

    Flow:
        1. Load market_candles for (instrument, timeframe, start_date, end_date)
        2. Load market_indicators for same range
        3. Inner-join on candle_time → unified chronological DataFrame
        4. Iterate row-by-row (no look-ahead):
           a. Build IndicatorRecord from current row
           b. Generate TradeAction via strategy
           c. Execute trade (open/close) through TradeExecutor
           d. Enforce risk limits via RiskEngine
           e. Mark portfolio to market (current close price)
           f. Snapshot equity curve
        5. Force-close any open position at end_date
        6. Compute performance metrics via PerformanceEngine
        7. Persist run summary, trades, snapshots to PostgreSQL
        8. Return BacktestResult
    """

    def __init__(self) -> None:
        self._perf = PerformanceEngine()

    def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute the full backtest. Returns BacktestResult."""
        create_backtest_tables()

        run_name = config.run_name or self._auto_run_name(config)
        logger.info("=" * 60)
        logger.info("  Backtest: %s", run_name)
        logger.info("  %s | %s | %s → %s", config.instrument, config.timeframe,
                    config.start_date.date(), config.end_date.date())
        logger.info("  Capital: %.2f | Strategy: %s", float(config.starting_capital),
                    config.strategy_name)
        logger.info("=" * 60)

        df = self._load_data(config)
        if df.empty:
            raise ValueError(
                f"No data found for {config.instrument} {config.timeframe} "
                f"between {config.start_date} and {config.end_date}. "
                "Run Phase 1 ingestion and Phase 2 indicator pipeline first."
            )

        logger.info("[BacktestEngine] Loaded %d rows for backtest", len(df))

        strategy = self._build_strategy(config)
        portfolio = Portfolio(config.starting_capital)
        executor = TradeExecutor(config)
        risk = RiskEngine(config)

        strategy.on_backtest_start()

        for candle_time, row in df.iterrows():
            current_price = Decimal(str(float(row["close"])))
            indicator = self._row_to_indicator(row, config.instrument, config.timeframe, candle_time)

            # Keep strategy's position state in sync (no-op for stateless strategies)
            strategy.set_position_state(portfolio.has_open_position)

            action = strategy.generate_signal(indicator, current_price)

            if action == TradeAction.OPEN_LONG:
                cash_req = executor.total_entry_cost(current_price, portfolio.cash)
                can_trade, reason = risk.can_open_trade(portfolio, candle_time, cash_req)
                if can_trade:
                    position = executor.open_long(
                        config.instrument, current_price, candle_time, portfolio.cash
                    )
                    if position is not None:
                        portfolio.enter_position(position)
                else:
                    logger.debug("[BacktestEngine] Trade blocked at %s: %s", candle_time, reason)

            elif action == TradeAction.CLOSE_LONG:
                position = portfolio.current_position
                if position:
                    trade = executor.close_long(position, current_price, candle_time)
                    portfolio.exit_position(trade)
                    risk.record_trade_pnl(trade)

            # Mark to market and snapshot every bar
            portfolio.mark_to_market({config.instrument: current_price})
            portfolio.snapshot(candle_time)

        # Force-close any open position at end of period
        if portfolio.has_open_position and not df.empty:
            last_time = df.index[-1]
            last_price = Decimal(str(float(df.iloc[-1]["close"])))
            forced = portfolio.force_close_all(
                {config.instrument: last_price}, last_time, executor
            )
            for t in forced:
                risk.record_trade_pnl(t)
            logger.info("[BacktestEngine] Force-closed %d position(s) at end of period", len(forced))
            portfolio.mark_to_market({config.instrument: last_price})
            portfolio.snapshot(last_time)

        strategy.on_backtest_end()

        result = self._perf.compute(
            config=config,
            trades=portfolio.closed_trades,
            equity_curve=portfolio.equity_curve,
            run_name=run_name,
        )

        run_id = self._save_run(result)
        if run_id:
            self._save_trades(run_id, portfolio.closed_trades)
            self._save_snapshots(run_id, portfolio.equity_curve)

        self._log_summary(result)
        return result

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self, config: BacktestConfig) -> pd.DataFrame:
        """Load candles + indicators, inner-join on candle_time, return sorted DataFrame."""
        with get_session() as session:
            candle_rows = session.execute(
                select(MarketCandle)
                .where(
                    MarketCandle.instrument == config.instrument,
                    MarketCandle.timeframe == config.timeframe,
                    MarketCandle.candle_time >= config.start_date,
                    MarketCandle.candle_time <= config.end_date,
                )
                .order_by(MarketCandle.candle_time.asc())
            ).scalars().all()

            indicator_rows = session.execute(
                select(MarketIndicator)
                .where(
                    MarketIndicator.instrument == config.instrument,
                    MarketIndicator.timeframe == config.timeframe,
                    MarketIndicator.candle_time >= config.start_date,
                    MarketIndicator.candle_time <= config.end_date,
                )
                .order_by(MarketIndicator.candle_time.asc())
            ).scalars().all()

        candle_data = {
            r.candle_time: {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume or 0),
            }
            for r in candle_rows
        }

        indicator_data = {
            r.candle_time: {
                # Phase 1
                "ema20": float(r.ema20) if r.ema20 is not None else None,
                "ema50": float(r.ema50) if r.ema50 is not None else None,
                "ema200": float(r.ema200) if r.ema200 is not None else None,
                "rsi14": float(r.rsi14) if r.rsi14 is not None else None,
                "vwap": float(r.vwap) if r.vwap is not None else None,
                "macd": float(r.macd) if r.macd is not None else None,
                "macd_signal": float(r.macd_signal) if r.macd_signal is not None else None,
                # Phase 4B
                "atr_14": float(r.atr_14) if r.atr_14 is not None else None,
                "adx_14": float(r.adx_14) if r.adx_14 is not None else None,
                "plus_di": float(r.plus_di) if r.plus_di is not None else None,
                "minus_di": float(r.minus_di) if r.minus_di is not None else None,
                "bb_middle": float(r.bb_middle) if r.bb_middle is not None else None,
                "bb_upper": float(r.bb_upper) if r.bb_upper is not None else None,
                "bb_lower": float(r.bb_lower) if r.bb_lower is not None else None,
                "bb_width": float(r.bb_width) if r.bb_width is not None else None,
                "supertrend": float(r.supertrend) if r.supertrend is not None else None,
                "supertrend_direction": int(r.supertrend_direction) if r.supertrend_direction is not None else None,
                "obv": float(r.obv) if r.obv is not None else None,
                "stoch_rsi_k": float(r.stoch_rsi_k) if r.stoch_rsi_k is not None else None,
                "stoch_rsi_d": float(r.stoch_rsi_d) if r.stoch_rsi_d is not None else None,
            }
            for r in indicator_rows
        }

        # Inner join: only process candle_times that have both candle and indicator
        common_times = sorted(set(candle_data) & set(indicator_data))
        if not common_times:
            return pd.DataFrame()

        rows = []
        for t in common_times:
            row = {**candle_data[t], **indicator_data[t]}
            rows.append(row)

        df = pd.DataFrame(rows, index=pd.DatetimeIndex(common_times))
        df.index.name = "candle_time"
        return df.sort_index()

    # ------------------------------------------------------------------
    # Helper: indicator record
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_indicator(
        row: pd.Series,
        instrument: str,
        timeframe: str,
        candle_time,
    ) -> IndicatorRecord:
        ts = candle_time.to_pydatetime() if hasattr(candle_time, "to_pydatetime") else candle_time
        sd = row.get("supertrend_direction")
        return IndicatorRecord(
            instrument=instrument,
            candle_time=ts,
            timeframe=timeframe,
            # Phase 1
            ema20=_to_dec(row.get("ema20")),
            ema50=_to_dec(row.get("ema50")),
            ema200=_to_dec(row.get("ema200")),
            rsi14=_to_dec(row.get("rsi14")),
            vwap=_to_dec(row.get("vwap")),
            macd=_to_dec(row.get("macd")),
            macd_signal=_to_dec(row.get("macd_signal")),
            # Phase 4B
            atr_14=_to_dec(row.get("atr_14")),
            adx_14=_to_dec(row.get("adx_14")),
            plus_di=_to_dec(row.get("plus_di")),
            minus_di=_to_dec(row.get("minus_di")),
            bb_middle=_to_dec(row.get("bb_middle")),
            bb_upper=_to_dec(row.get("bb_upper")),
            bb_lower=_to_dec(row.get("bb_lower")),
            bb_width=_to_dec(row.get("bb_width")),
            supertrend=_to_dec(row.get("supertrend")),
            supertrend_direction=int(sd) if sd is not None else None,
            obv=_to_dec(row.get("obv")),
            stoch_rsi_k=_to_dec(row.get("stoch_rsi_k")),
            stoch_rsi_d=_to_dec(row.get("stoch_rsi_d")),
        )

    # ------------------------------------------------------------------
    # Strategy factory
    # ------------------------------------------------------------------

    def _build_strategy(self, config: BacktestConfig) -> Strategy:
        name = config.strategy_name.lower()
        if name == "signal":
            return SignalToTradeAdapter()

        from strategies.registry import get_strategy, list_strategies
        from strategies.backtest_adapter import StrategyBacktestAdapter
        from strategies.multi_timeframe_base import MultiTimeframeStrategy
        from strategies.backtest_mtf_adapter import MultiTimeframeBacktestAdapter
        from confluence.timeframe_alignment import TimeframeAlignmentService

        try:
            strat = get_strategy(name)
        except KeyError:
            available = ["signal"] + list_strategies()
            raise ValueError(
                f"Unknown strategy '{config.strategy_name}'. "
                f"Available strategies: {', '.join(available)}"
            )

        if isinstance(strat, MultiTimeframeStrategy):
            # Override strategy timeframes from CLI if provided
            if config.trend_timeframe:
                strat._trend_tf = config.trend_timeframe
            if config.setup_timeframe:
                strat._setup_tf = config.setup_timeframe
            if config.entry_timeframe:
                strat._entry_tf = config.entry_timeframe

            all_indicators = self._load_mtf_indicators(config, strat)
            return MultiTimeframeBacktestAdapter(
                strategy=strat,
                all_indicators=all_indicators,
                alignment_service=TimeframeAlignmentService(),
            )

        return StrategyBacktestAdapter(strat)

    def _load_mtf_indicators(
        self,
        config: BacktestConfig,
        strategy: "MultiTimeframeStrategy",
    ) -> dict[str, list[IndicatorRecord]]:
        """Load IndicatorRecord lists for all timeframes required by an MTF strategy.

        Fetches a 30-day buffer before ``config.start_date`` so that
        alignment can find valid higher-timeframe bars even at the very
        start of the backtest window.
        """
        timeframes = {
            strategy.trend_timeframe,
            strategy.setup_timeframe,
            strategy.entry_timeframe,
        }
        buffer_start = config.start_date - timedelta(days=30)
        result: dict[str, list[IndicatorRecord]] = {}

        for tf in timeframes:
            with get_session() as session:
                rows = session.execute(
                    select(MarketIndicator)
                    .where(
                        MarketIndicator.instrument == config.instrument,
                        MarketIndicator.timeframe == tf,
                        MarketIndicator.candle_time >= buffer_start,
                        MarketIndicator.candle_time <= config.end_date,
                    )
                    .order_by(MarketIndicator.candle_time.asc())
                ).scalars().all()

            result[tf] = [self._db_row_to_indicator(row) for row in rows]
            logger.info(
                "[BacktestEngine] Loaded %d indicator rows for %s %s",
                len(result[tf]), config.instrument, tf,
            )

        return result

    @staticmethod
    def _db_row_to_indicator(row: MarketIndicator) -> IndicatorRecord:
        """Convert a ``MarketIndicator`` ORM row to an ``IndicatorRecord`` with all fields."""
        sd = row.supertrend_direction
        return IndicatorRecord(
            instrument=row.instrument,
            candle_time=row.candle_time,
            timeframe=row.timeframe,
            ema20=_to_dec(row.ema20),
            ema50=_to_dec(row.ema50),
            ema200=_to_dec(row.ema200),
            rsi14=_to_dec(row.rsi14),
            vwap=_to_dec(row.vwap),
            macd=_to_dec(row.macd),
            macd_signal=_to_dec(row.macd_signal),
            atr_14=_to_dec(row.atr_14),
            adx_14=_to_dec(row.adx_14),
            plus_di=_to_dec(row.plus_di),
            minus_di=_to_dec(row.minus_di),
            bb_middle=_to_dec(row.bb_middle),
            bb_upper=_to_dec(row.bb_upper),
            bb_lower=_to_dec(row.bb_lower),
            bb_width=_to_dec(row.bb_width),
            supertrend=_to_dec(row.supertrend),
            supertrend_direction=int(sd) if sd is not None else None,
            obv=_to_dec(row.obv),
            stoch_rsi_k=_to_dec(row.stoch_rsi_k),
            stoch_rsi_d=_to_dec(row.stoch_rsi_d),
        )

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    def _save_run(self, result: BacktestResult) -> Optional[int]:
        try:
            with get_session() as session:
                run = BacktestRun(
                    run_name=result.run_name,
                    strategy_name=result.strategy_name,
                    instrument=result.instrument,
                    timeframe=result.timeframe,
                    start_date=result.start_date,
                    end_date=result.end_date,
                    starting_capital=float(result.starting_capital),
                    ending_capital=float(result.ending_capital),
                    total_return_pct=float(result.total_return_pct),
                    max_drawdown_pct=float(result.max_drawdown_pct),
                    win_rate_pct=float(result.win_rate_pct),
                    sharpe_ratio=float(result.sharpe_ratio),
                )
                session.add(run)
                session.flush()
                run_id = run.id
                logger.info("[BacktestEngine] Saved run id=%d: %s", run_id, result.run_name)
                return run_id
        except Exception as exc:
            logger.error("[BacktestEngine] Failed to save run: %s", exc)
            return None

    def _save_trades(self, run_id: int, trades: list[Trade]) -> None:
        if not trades:
            return
        rows = [
            {
                "run_id": run_id,
                "instrument": t.instrument,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "quantity": t.quantity,
                "side": t.side.value,
                "gross_pnl": float(t.gross_pnl),
                "net_pnl": float(t.net_pnl),
                "commission": float(t.commission),
                "slippage": float(t.slippage),
                "holding_minutes": t.holding_minutes,
            }
            for t in trades
        ]
        try:
            with get_session() as session:
                session.execute(pg_insert(BacktestTrade).values(rows))
            logger.info("[BacktestEngine] Saved %d trade records for run %d", len(rows), run_id)
        except Exception as exc:
            logger.error("[BacktestEngine] Failed to save trades: %s", exc)

    def _save_snapshots(self, run_id: int, equity_curve: list, batch_size: int = 500) -> None:
        if not equity_curve:
            return
        rows = [
            {
                "run_id": run_id,
                "snapshot_time": ep.snapshot_time,
                "cash": float(ep.cash),
                "equity": float(ep.equity),
                "unrealized_pnl": float(ep.unrealized_pnl),
                "realized_pnl": float(ep.realized_pnl),
                "drawdown_pct": float(ep.drawdown_pct),
            }
            for ep in equity_curve
        ]
        try:
            for i in range(0, len(rows), batch_size):
                batch = rows[i: i + batch_size]
                with get_session() as session:
                    session.execute(pg_insert(PortfolioSnapshot).values(batch))
            logger.info("[BacktestEngine] Saved %d snapshots for run %d", len(rows), run_id)
        except Exception as exc:
            logger.error("[BacktestEngine] Failed to save snapshots: %s", exc)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_run_name(config: BacktestConfig) -> str:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        instr = config.instrument.replace(" ", "_").replace("/", "-")
        return f"{config.strategy_name}_{instr}_{config.timeframe}_{ts}"

    @staticmethod
    def _log_summary(result: BacktestResult) -> None:
        logger.info("─" * 60)
        logger.info("  BACKTEST COMPLETE: %s", result.run_name)
        logger.info("  Total Return    : %.2f%%", float(result.total_return_pct))
        logger.info("  CAGR            : %.2f%%", float(result.cagr_pct))
        logger.info("  Max Drawdown    : %.2f%%", float(result.max_drawdown_pct))
        logger.info("  Sharpe Ratio    : %.4f", float(result.sharpe_ratio))
        logger.info("  Win Rate        : %.2f%%", float(result.win_rate_pct))
        logger.info("  Total Trades    : %d", result.total_trades)
        logger.info("  Profit Factor   : %.4f", float(result.profit_factor))
        logger.info("─" * 60)
