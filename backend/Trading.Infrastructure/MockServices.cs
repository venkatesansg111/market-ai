using Trading.Contracts;
using Trading.Domain;

namespace Trading.Infrastructure;

/// <summary>
/// In-memory mock services that supply realistic demo data.
/// Replace with real Python-bridge implementations for production.
/// </summary>
public class MockPortfolioService : IPortfolioService
{
    private static readonly Random _rng = new(42);

    public Task<PortfolioDto> GetPortfolioAsync() => Task.FromResult(new PortfolioDto(
        Equity: 1_024_500m,
        Cash: 312_000m,
        UnrealizedPnl: 8_200m,
        RealizedPnl: 45_300m,
        DailyPnl: 2_150m,
        DrawdownPct: 3.2,
        Exposure: 712_500m,
        Leverage: 1.4,
        Timestamp: DateTime.UtcNow
    ));

    public Task<PortfolioHistoryDto> GetHistoryAsync(int days = 30)
    {
        var base_ = 980_000m;
        var equity = new List<EquityPoint>();
        var dd = new List<EquityPoint>();
        var peak = base_;
        for (int i = days; i >= 0; i--)
        {
            var t = DateTime.UtcNow.AddDays(-i);
            var v = base_ + (decimal)(_rng.NextDouble() * 50000 - 10000) * (days - i + 1) / days;
            equity.Add(new EquityPoint(t, v));
            if (v > peak) peak = v;
            dd.Add(new EquityPoint(t, peak == 0 ? 0 : (v - peak) / peak * 100));
        }
        return Task.FromResult(new PortfolioHistoryDto(equity, dd));
    }

    public Task<ExposureDto> GetExposureAsync() => Task.FromResult(new ExposureDto(
        BySymbol: new() { ["RELIANCE"] = 180_000m, ["TCS"] = 150_000m, ["INFY"] = 120_000m, ["HDFC"] = 140_000m, ["SBIN"] = 122_500m },
        BySector: new() { ["Technology"] = 270_000m, ["Finance"] = 262_500m, ["Energy"] = 180_000m },
        ByStrategy: new() { ["momentum"] = 350_000m, ["mean_reversion"] = 250_000m, ["trend_follow"] = 112_500m }
    ));

    public Task<List<PositionDto>> GetPositionsAsync() => Task.FromResult(new List<PositionDto>
    {
        new("RELIANCE", 100, 2800m, 2850m, 5000m, 285_000m, "LONG"),
        new("TCS", 75, 3900m, 3950m, 3750m, 296_250m, "LONG"),
        new("INFY", 120, 1480m, 1500m, 2400m, 180_000m, "LONG"),
        new("HDFC", 80, 1700m, 1720m, 1600m, 137_600m, "LONG"),
        new("SBIN", 200, 600m, 612.5m, 2500m, 122_500m, "LONG"),
    });

    public Task<PositionDto?> GetPositionAsync(string symbol)
    {
        var all = GetPositionsAsync().Result;
        return Task.FromResult(all.FirstOrDefault(p => p.Symbol.Equals(symbol, StringComparison.OrdinalIgnoreCase)));
    }
}

public class MockOrderService : IOrderService
{
    private static readonly List<OrderDto> _orders = new()
    {
        new("ORD-001", "RELIANCE", "BUY",  100, "MARKET", "FILLED",  "momentum",      DateTime.UtcNow.AddHours(-5),  DateTime.UtcNow.AddHours(-5),  2800m,  7m),
        new("ORD-002", "TCS",      "BUY",  75,  "LIMIT",  "FILLED",  "momentum",      DateTime.UtcNow.AddHours(-4),  DateTime.UtcNow.AddHours(-4),  3900m,  5.85m),
        new("ORD-003", "INFY",     "BUY",  120, "MARKET", "FILLED",  "mean_reversion",DateTime.UtcNow.AddHours(-3),  DateTime.UtcNow.AddHours(-3),  1480m,  3.55m),
        new("ORD-004", "HDFC",     "BUY",  80,  "MARKET", "FILLED",  "trend_follow",  DateTime.UtcNow.AddHours(-2),  DateTime.UtcNow.AddHours(-2),  1700m,  2.72m),
        new("ORD-005", "SBIN",     "BUY",  200, "LIMIT",  "PENDING", "momentum",      DateTime.UtcNow.AddMinutes(-30), null, null, null),
    };

    private static readonly List<TradeDto> _trades = new()
    {
        new("TRD-001", "RELIANCE", "momentum",      "BUY", 100, 2800m, null,   null,    7m,    DateTime.UtcNow.AddHours(-5), null),
        new("TRD-002", "TCS",      "momentum",      "BUY", 75,  3900m, null,   null,    5.85m, DateTime.UtcNow.AddHours(-4), null),
        new("TRD-003", "WIPRO",    "mean_reversion","SELL",50,  480m,  475m,   -250m,   2.4m,  DateTime.UtcNow.AddDays(-1),  DateTime.UtcNow.AddDays(-1).AddHours(2)),
        new("TRD-004", "BAJAJ",    "trend_follow",  "SELL",30,  7200m, 7380m,  5400m,   8.1m,  DateTime.UtcNow.AddDays(-2),  DateTime.UtcNow.AddDays(-2).AddHours(3)),
    };

    public Task<List<OrderDto>> GetOrdersAsync(string? status = null, string? symbol = null)
    {
        var q = _orders.AsEnumerable();
        if (status != null) q = q.Where(o => o.Status.Equals(status, StringComparison.OrdinalIgnoreCase));
        if (symbol != null) q = q.Where(o => o.Symbol.Equals(symbol, StringComparison.OrdinalIgnoreCase));
        return Task.FromResult(q.ToList());
    }

    public Task<OrderDto?> GetOrderAsync(string orderId) =>
        Task.FromResult(_orders.FirstOrDefault(o => o.OrderId.Equals(orderId, StringComparison.OrdinalIgnoreCase)));

    public Task<bool> CancelOrderAsync(string orderId) => Task.FromResult(true);

    public Task<List<TradeDto>> GetTradesAsync(string? symbol = null, string? strategy = null)
    {
        var q = _trades.AsEnumerable();
        if (symbol != null) q = q.Where(t => t.Symbol.Equals(symbol, StringComparison.OrdinalIgnoreCase));
        if (strategy != null) q = q.Where(t => t.Strategy.Equals(strategy, StringComparison.OrdinalIgnoreCase));
        return Task.FromResult(q.ToList());
    }

    public Task<TradeDto?> GetTradeAsync(string tradeId) =>
        Task.FromResult(_trades.FirstOrDefault(t => t.TradeId.Equals(tradeId, StringComparison.OrdinalIgnoreCase)));
}

public class MockStrategyService : IStrategyService
{
    private static readonly List<StrategyDto> _strategies = new()
    {
        new("momentum",       "active",   "bullish",     1.82, 2.1,  0.58, 0.032, 1.95, 142, 45, 0.71),
        new("mean_reversion", "active",   "ranging",     1.24, 1.55, 0.52, 0.055, 1.62, 98,  32, 0.64),
        new("trend_follow",   "active",   "bullish",     1.45, 1.78, 0.55, 0.041, 1.75, 76,  28, 0.68),
        new("volatility_arb", "inactive", "neutral",     0.0,  0.0,  0.0,  0.0,   0.0,  0,   0,  0.0),
    };

    public Task<List<StrategyDto>> GetStrategiesAsync()   => Task.FromResult(_strategies);
    public Task<List<StrategyDto>> GetPerformanceAsync()  => Task.FromResult(_strategies);

    public Task<List<RegimeTimelineDto>> GetRegimesAsync() => Task.FromResult(new List<RegimeTimelineDto>
    {
        new("momentum", new()
        {
            new("ranging",  0.6, DateTime.UtcNow.AddDays(-7), DateTime.UtcNow.AddDays(-3)),
            new("bullish",  0.8, DateTime.UtcNow.AddDays(-3), null),
        }),
        new("mean_reversion", new()
        {
            new("bearish",  0.7, DateTime.UtcNow.AddDays(-14), DateTime.UtcNow.AddDays(-7)),
            new("ranging",  0.6, DateTime.UtcNow.AddDays(-7),  null),
        }),
    });

    public Task<bool> EnableStrategyAsync(string name)  => Task.FromResult(true);
    public Task<bool> DisableStrategyAsync(string name) => Task.FromResult(true);
}

public class MockRiskService : IRiskService
{
    public Task<RiskDto> GetRiskAsync() => Task.FromResult(new RiskDto(
        TotalExposure: 712_500m,
        Leverage: 1.4,
        DrawdownPct: 3.2,
        DailyLoss: -2_150m,
        VaR95: 18_500m,
        TradingHalted: false,
        ActiveAlerts: new()
        {
            new("ALT-001", "Leverage Warning", "Leverage approaching threshold", "WARNING", "PORTFOLIO", DateTime.UtcNow.AddMinutes(-15)),
        }
    ));

    public Task<ExposureDto> GetExposureAsync() => new MockPortfolioService().GetExposureAsync();

    public Task<List<RiskAlertDto>> GetAlertsAsync() => Task.FromResult(new List<RiskAlertDto>
    {
        new("ALT-001", "Leverage Warning",   "Leverage 1.4x approaching 2x threshold", "WARNING",  "PORTFOLIO", DateTime.UtcNow.AddMinutes(-15)),
        new("ALT-002", "Drawdown Monitor",   "Current drawdown 3.2%",                   "INFO",     "PORTFOLIO", DateTime.UtcNow.AddMinutes(-5)),
    });

    public Task<bool> UpdateRiskLimitsAsync(string limitType, decimal value) => Task.FromResult(true);
}

public class MockExplainabilityService : IExplainabilityService
{
    public Task<TradeExplanationDto?> ExplainTradeAsync(string tradeId) => Task.FromResult<TradeExplanationDto?>(
        tradeId == "TRD-001" ? _explanation : null
    );

    private static readonly TradeExplanationDto _explanation = new(
        TradeId: "TRD-001",
        Symbol: "RELIANCE",
        Strategy: "momentum",
        Action: "BUY",
        Regime: "bullish",
        SignalConfidence: 0.82,
        RiskScore: 0.05,
        RiskDecision: "APPROVED",
        RiskReason: "All risk checks passed. Position within limits.",
        PositionSizeReason: "Fixed fractional 1% of equity at current volatility (ATR=28).",
        ExecutionReason: "Market order submitted. Filled at 2800 within 0.1% of signal price.",
        FillPrice: 2800m,
        FillQuantity: 100,
        Timestamp: DateTime.UtcNow.AddHours(-5),
        DecisionChain: new()
        {
            new("TICK",      "Tick received: RELIANCE @ 2798.5",                       DateTime.UtcNow.AddHours(-5).AddSeconds(-3)),
            new("CANDLE",    "1-minute candle closed bullish (O:2795 H:2802 C:2800)",  DateTime.UtcNow.AddHours(-5).AddSeconds(-2)),
            new("INDICATOR", "EMA crossover confirmed, RSI=62, regime=bullish",         DateTime.UtcNow.AddHours(-5).AddSeconds(-1)),
            new("SIGNAL",    "BUY signal generated (confidence=0.82)",                  DateTime.UtcNow.AddHours(-5)),
            new("RISK",      "Risk gate APPROVED 100 shares",                           DateTime.UtcNow.AddHours(-5).AddSeconds(1)),
            new("ORDER",     "Market order ORD-001 submitted",                          DateTime.UtcNow.AddHours(-5).AddSeconds(2)),
            new("FILL",      "Order filled @ 2800.0, commission=7.0",                  DateTime.UtcNow.AddHours(-5).AddSeconds(3)),
            new("PORTFOLIO", "Portfolio updated: equity=1022350, unrealizedPnl=0",     DateTime.UtcNow.AddHours(-5).AddSeconds(4)),
        }
    );

    public Task<List<TradeExplanationDto>> ExplainAllTradesAsync() =>
        Task.FromResult(new List<TradeExplanationDto> { _explanation });
}

public class MockReplayService : IReplayService
{
    private static string _status = "stopped";
    private static double _speed = 1.0;

    public Task<ReplayStatusDto> GetStatusAsync() => Task.FromResult(new ReplayStatusDto(
        Status: _status, Speed: _speed, TotalEvents: 1500, ProcessedEvents: 0, CurrentTime: null
    ));

    public Task<bool> StartAsync(double speed = 1.0)  { _status = "running"; _speed = speed; return Task.FromResult(true); }
    public Task<bool> PauseAsync()  { _status = "paused";  return Task.FromResult(true); }
    public Task<bool> StopAsync()   { _status = "stopped"; return Task.FromResult(true); }
}

public class MockSystemHealthService : ISystemHealthService
{
    public Task<SystemHealthDto> GetHealthAsync() => Task.FromResult(new SystemHealthDto(
        Status: "healthy",
        UptimeSeconds: 3600 * 4,
        PublishCount: 48_320,
        ErrorCount: 2,
        EventsPerSecond: 12.5,
        ActiveSubscriptions: 18,
        Timestamp: DateTime.UtcNow
    ));
}

public class MockAlertService : IAlertService
{
    private static readonly List<AlertDto> _alerts = new()
    {
        new("ALT-001", "Drawdown Warning",      "Drawdown at 3.2% approaching 5% threshold", "WARNING",  "PORTFOLIO", DateTime.UtcNow.AddMinutes(-30), false, new() { ["drawdown_pct"] = (object)3.2 }),
        new("ALT-002", "Low Signal Confidence", "Strategy mean_reversion avg confidence 0.52","WARNING",  "STRATEGY",  DateTime.UtcNow.AddMinutes(-15), false, new() { ["confidence"]   = (object)0.52 }),
        new("ALT-003", "System Start",          "Trading platform started successfully",       "INFO",     "SYSTEM",    DateTime.UtcNow.AddHours(-4),    true,  new()),
    };

    public Task<List<AlertDto>> GetAlertsAsync(string? severity = null, string? category = null)
    {
        var q = _alerts.AsEnumerable();
        if (severity != null) q = q.Where(a => a.Severity.Equals(severity, StringComparison.OrdinalIgnoreCase));
        if (category != null) q = q.Where(a => a.Category.Equals(category, StringComparison.OrdinalIgnoreCase));
        return Task.FromResult(q.ToList());
    }

    public Task<bool> AcknowledgeAlertAsync(string alertId)
    {
        var a = _alerts.FirstOrDefault(x => x.AlertId == alertId);
        if (a == null) return Task.FromResult(false);
        var idx = _alerts.IndexOf(a);
        _alerts[idx] = a with { Acknowledged = true };
        return Task.FromResult(true);
    }
}

public class MockMarketDataService : IMarketDataService
{
    private static readonly Random _rng = new(42);
    private static readonly string[] _nse = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "WIPRO", "BAJAJFINSV", "SBIN", "ITC", "KOTAKBANK"];
    private static readonly string[] _bse = ["SENSEX", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"];

    public Task<List<WatchlistItemDto>> GetWatchlistAsync(string exchange = "NSE")
    {
        var symbols = exchange.Equals("BSE", StringComparison.OrdinalIgnoreCase) ? _bse : _nse;
        var items = symbols.Select(s => new WatchlistItemDto(
            Symbol: s,
            Price: 1000m + (decimal)(_rng.NextDouble() * 3000),
            ChangePercent: _rng.NextDouble() * 4 - 2,
            Volume: _rng.NextInt64(500_000, 5_000_000),
            High:  1000m + (decimal)(_rng.NextDouble() * 3100),
            Low:   900m  + (decimal)(_rng.NextDouble() * 2900)
        )).ToList();
        return Task.FromResult(items);
    }

    public Task<List<CandleDto>> GetCandlesAsync(string symbol, string timeframe, int limit = 100)
    {
        var candles = new List<CandleDto>();
        var price = 2000m + (decimal)(_rng.NextDouble() * 1000);
        for (int i = limit; i >= 0; i--)
        {
            var t = DateTime.UtcNow.AddMinutes(-i);
            var o = price;
            var c = o + (decimal)(_rng.NextDouble() * 40 - 20);
            var h = Math.Max(o, c) + (decimal)(_rng.NextDouble() * 10);
            var l = Math.Min(o, c) - (decimal)(_rng.NextDouble() * 10);
            candles.Add(new CandleDto(symbol, timeframe, o, h, l, c, _rng.NextInt64(1000, 50000), t));
            price = c;
        }
        return Task.FromResult(candles);
    }

    public Task<TickDto?> GetLatestTickAsync(string symbol) => Task.FromResult<TickDto?>(
        new TickDto(symbol, 2850m, 123_456, 2849.5m, 2850.5m, DateTime.UtcNow)
    );
}

public class MockPnLAttributionService : IPnLAttributionService
{
    public Task<PnLAttributionDto> GetAttributionAsync() => Task.FromResult(new PnLAttributionDto(
        ByStrategy: new() { ["momentum"] = 28_500m, ["mean_reversion"] = 12_200m, ["trend_follow"] = 4_600m },
        ByAsset: new() { ["RELIANCE"] = 15_000m, ["TCS"] = 12_000m, ["BAJAJ"] = 8_300m, ["INFY"] = 5_400m, ["HDFC"] = 4_600m },
        ByRegime: new() { ["bullish"] = 32_000m, ["ranging"] = 8_500m, ["bearish"] = 4_800m },
        ByDay: new() {
            [DateTime.UtcNow.AddDays(-6).ToString("yyyy-MM-dd")] = 3_200m,
            [DateTime.UtcNow.AddDays(-5).ToString("yyyy-MM-dd")] = 7_800m,
            [DateTime.UtcNow.AddDays(-4).ToString("yyyy-MM-dd")] = -1_200m,
            [DateTime.UtcNow.AddDays(-3).ToString("yyyy-MM-dd")] = 9_500m,
            [DateTime.UtcNow.AddDays(-2).ToString("yyyy-MM-dd")] = 4_300m,
            [DateTime.UtcNow.AddDays(-1).ToString("yyyy-MM-dd")] = 3_700m,
            [DateTime.UtcNow.ToString("yyyy-MM-dd")]             = 2_150m,
        },
        TotalPnl: 45_300m,
        TradeCount: 32
    ));
}

public class MockAdminService : IAdminService
{
    public Task<AdminActionResponse> ExecuteActionAsync(AdminActionRequest request) =>
        Task.FromResult(new AdminActionResponse(true, $"Action '{request.Action}' executed successfully"));

    public Task<bool> PauseTradingAsync()  => Task.FromResult(true);
    public Task<bool> ResumeTradingAsync() => Task.FromResult(true);
    public Task<bool> KillSwitchAsync()    => Task.FromResult(true);
}

public class MockAuditService : IAuditService
{
    private static readonly List<AuditLogEntry> _logs = new()
    {
        new("AUD-001", "admin",  "LOGIN",            "Admin logged in",                    DateTime.UtcNow.AddHours(-4)),
        new("AUD-002", "admin",  "STRATEGY_ENABLE",  "Enabled momentum strategy",          DateTime.UtcNow.AddHours(-3)),
        new("AUD-003", "trader", "RISK_LIMIT_UPDATE","Updated max drawdown to 10%",        DateTime.UtcNow.AddHours(-2)),
        new("AUD-004", "admin",  "KILL_SWITCH",      "Emergency kill switch not activated", DateTime.UtcNow.AddHours(-1)),
    };

    public Task LogActionAsync(string userId, string action, string details)
    {
        _logs.Add(new AuditLogEntry(Guid.NewGuid().ToString(), userId, action, details, DateTime.UtcNow));
        return Task.CompletedTask;
    }

    public Task<List<AuditLogEntry>> GetLogsAsync(int limit = 100) =>
        Task.FromResult(_logs.TakeLast(limit).ToList());
}
