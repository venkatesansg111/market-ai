namespace Trading.Contracts;

public record PortfolioDto(
    decimal Equity,
    decimal Cash,
    decimal UnrealizedPnl,
    decimal RealizedPnl,
    decimal DailyPnl,
    double DrawdownPct,
    decimal Exposure,
    double Leverage,
    DateTime Timestamp
);

public record PositionDto(
    string Symbol,
    int Quantity,
    decimal AvgPrice,
    decimal CurrentPrice,
    decimal UnrealizedPnl,
    decimal MarketValue,
    string Side
);

public record OrderDto(
    string OrderId,
    string Symbol,
    string Action,
    int Quantity,
    string OrderType,
    string Status,
    string StrategyName,
    DateTime CreatedAt,
    DateTime? FilledAt,
    decimal? FillPrice,
    decimal? Commission
);

public record TradeDto(
    string TradeId,
    string Symbol,
    string Strategy,
    string Action,
    int Quantity,
    decimal EntryPrice,
    decimal? ExitPrice,
    decimal? RealizedPnl,
    decimal Commission,
    DateTime EntryTime,
    DateTime? ExitTime
);

public record StrategyDto(
    string Name,
    string Status,
    string CurrentRegime,
    double Sharpe,
    double Sortino,
    double WinRate,
    double Drawdown,
    double ProfitFactor,
    int TotalSignals,
    int TotalTrades,
    double AvgConfidence
);

public record RiskDto(
    decimal TotalExposure,
    double Leverage,
    double DrawdownPct,
    decimal DailyLoss,
    decimal VaR95,
    bool TradingHalted,
    List<RiskAlertDto> ActiveAlerts
);

public record RiskAlertDto(
    string AlertId,
    string Title,
    string Message,
    string Severity,
    string Category,
    DateTime Timestamp
);

public record ExposureDto(
    Dictionary<string, decimal> BySymbol,
    Dictionary<string, decimal> BySector,
    Dictionary<string, decimal> ByStrategy
);

public record TradeExplanationDto(
    string TradeId,
    string Symbol,
    string Strategy,
    string Action,
    string Regime,
    double SignalConfidence,
    double RiskScore,
    string RiskDecision,
    string RiskReason,
    string PositionSizeReason,
    string ExecutionReason,
    decimal? FillPrice,
    int FillQuantity,
    DateTime Timestamp,
    List<DecisionStepDto> DecisionChain
);

public record DecisionStepDto(
    string StepType,
    string Description,
    DateTime Timestamp
);

public record ReplayStatusDto(
    string Status,
    double Speed,
    int TotalEvents,
    int ProcessedEvents,
    DateTime? CurrentTime
);

public record SystemHealthDto(
    string Status,
    double UptimeSeconds,
    long PublishCount,
    int ErrorCount,
    double EventsPerSecond,
    int ActiveSubscriptions,
    DateTime Timestamp
);

public record AlertDto(
    string AlertId,
    string Title,
    string Message,
    string Severity,
    string Category,
    DateTime Timestamp,
    bool Acknowledged,
    Dictionary<string, object> Metadata
);

public record LoginRequest(string Username, string Password);
public record LoginResponse(string Token, string Role, string Username, DateTime ExpiresAt);

public record AdminActionRequest(string Action, string? Target = null, string? Value = null);
public record AdminActionResponse(bool Success, string Message);

public record CandleDto(
    string Symbol,
    string Timeframe,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close,
    long Volume,
    DateTime Timestamp
);

public record TickDto(
    string Symbol,
    decimal Price,
    long Volume,
    decimal? Bid,
    decimal? Ask,
    DateTime Timestamp
);

public record PnLAttributionDto(
    Dictionary<string, decimal> ByStrategy,
    Dictionary<string, decimal> ByAsset,
    Dictionary<string, decimal> ByRegime,
    Dictionary<string, decimal> ByDay,
    decimal TotalPnl,
    int TradeCount
);

public record PerformanceMetricsDto(
    double? Sharpe,
    double? Sortino,
    double? Calmar,
    double WinRate,
    double ProfitFactor,
    int TotalTrades,
    decimal TotalPnl
);

public record ExecutionMetricsDto(
    double FillRate,
    decimal TotalCommission,
    decimal? AvgFillPrice,
    int TotalOrders,
    int FilledOrders
);

public record PortfolioHistoryDto(
    List<EquityPoint> EquityCurve,
    List<EquityPoint> DrawdownCurve
);

public record EquityPoint(DateTime Timestamp, decimal Value);

public record WatchlistItemDto(
    string Symbol,
    decimal Price,
    double ChangePercent,
    long Volume,
    decimal High,
    decimal Low
);

public record RegimeTimelineDto(
    string Strategy,
    List<RegimeEntry> Entries
);

public record RegimeEntry(
    string Regime,
    double Strength,
    DateTime StartTime,
    DateTime? EndTime
);

// ── Options Chain ─────────────────────────────────────────────────────────────
public record OptionLegDto(
    long Oi, long OiChange, long Volume,
    double Iv, decimal Ltp, decimal NetChange,
    long BidQty, decimal Bid, decimal Ask, long AskQty,
    decimal Delta, decimal Gamma, decimal Theta, decimal Vega
);

public record OptionsChainRowDto(
    decimal Strike, bool IsAtm, bool IsCeItm, bool IsPeItm,
    OptionLegDto Ce, OptionLegDto Pe
);

public record OptionsChainDto(
    string Symbol, decimal SpotPrice, string Expiry,
    decimal AtmStrike, List<OptionsChainRowDto> Rows
);

public record OptionsExpiryDto(string Expiry, string Label, string ExpiryType);

// ── AI Predictions ────────────────────────────────────────────────────────────
public record PredictionDto(
    string Symbol, string Signal, string OptionType,
    decimal Strike, string Expiry, double Confidence,
    string Regime, decimal TargetPrice, decimal StopLoss,
    string Timeframe, double ExpectedReturn, double RiskReward,
    string Reason, DateTime GeneratedAt
);
