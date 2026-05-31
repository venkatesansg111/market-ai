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
    private static readonly string[] _nse = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "WIPRO", "BAJAJFINSV", "SBIN", "ITC", "KOTAKBANK"];
    private static readonly string[] _bse = ["SENSEX", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"];

    private static readonly Dictionary<string, decimal> _basePrices = new()
    {
        ["RELIANCE"]   = 2850.00m, ["TCS"]        = 4052.75m, ["INFY"]       = 1521.40m,
        ["HDFCBANK"]   = 1725.90m, ["ICICIBANK"]  = 1238.65m, ["WIPRO"]      = 582.30m,
        ["BAJAJFINSV"] = 1682.45m, ["SBIN"]       = 812.80m,  ["ITC"]        = 478.25m,
        ["KOTAKBANK"]  = 1876.10m, ["SENSEX"]     = 80540.00m,["NIFTY50"]    = 24502.55m,
    };
    private static readonly Dictionary<string, decimal> _prevClose = new()
    {
        ["RELIANCE"]   = 2823.50m, ["TCS"]        = 4028.00m, ["INFY"]       = 1498.20m,
        ["HDFCBANK"]   = 1701.30m, ["ICICIBANK"]  = 1219.80m, ["WIPRO"]      = 574.55m,
        ["BAJAJFINSV"] = 1655.90m, ["SBIN"]       = 799.40m,  ["ITC"]        = 472.10m,
        ["KOTAKBANK"]  = 1851.70m, ["SENSEX"]     = 79830.00m,["NIFTY50"]    = 24180.00m,
    };

    private static decimal StablePrice(string symbol)
    {
        var seed = (symbol + DateTime.UtcNow.ToString("yyyyMMddHHmm")).GetHashCode();
        var rng  = new Random(seed);
        var base_ = _basePrices.GetValueOrDefault(symbol, 1000m);
        return Math.Round(base_ * (1m + (decimal)(rng.NextDouble() * 0.014 - 0.007)), 2);
    }

    public Task<List<WatchlistItemDto>> GetWatchlistAsync(string exchange = "NSE")
    {
        var symbols = exchange.Equals("BSE", StringComparison.OrdinalIgnoreCase) ? _bse : _nse;
        var items = symbols.Select(s =>
        {
            var price = StablePrice(s);
            var prev  = _prevClose.GetValueOrDefault(s, price * 0.99m);
            var chg   = (double)((price - prev) / prev * 100);
            var seed2 = (s + "vol" + DateTime.UtcNow.ToString("yyyyMMddHH")).GetHashCode();
            var rng2  = new Random(seed2);
            return new WatchlistItemDto(
                Symbol: s, Price: price,
                ChangePercent: Math.Round(chg, 2),
                Volume: rng2.NextInt64(500_000, 5_000_000),
                High: Math.Round(price * 1.008m, 2),
                Low:  Math.Round(price * 0.992m, 2)
            );
        }).ToList();
        return Task.FromResult(items);
    }

    public Task<List<CandleDto>> GetCandlesAsync(string symbol, string timeframe, int limit = 100)
    {
        var seed = (symbol + timeframe).GetHashCode();
        var rng  = new Random(seed);
        var candles = new List<CandleDto>();
        var basePrice = _basePrices.GetValueOrDefault(symbol, 2000m);
        var price = basePrice * 0.97m;
        var minuteStep = timeframe switch { "5m" => 5, "15m" => 15, "1h" => 60, "1D" => 1440, _ => 1 };
        for (int i = limit; i >= 0; i--)
        {
            var t  = DateTime.UtcNow.AddMinutes(-(i * minuteStep));
            // Deterministic jitter seeded by candle index so history is stable
            var cseed = (symbol + timeframe + i.ToString()).GetHashCode();
            var crng  = new Random(cseed);
            var move  = (decimal)(crng.NextDouble() * 0.008 - 0.003);
            price += price * move;
            var o = price;
            var c = price + price * (decimal)(crng.NextDouble() * 0.006 - 0.003);
            var h = Math.Max(o, c) + price * (decimal)(crng.NextDouble() * 0.003);
            var l = Math.Min(o, c) - price * (decimal)(crng.NextDouble() * 0.003);
            candles.Add(new CandleDto(symbol, timeframe,
                Math.Round(o, 2), Math.Round(h, 2), Math.Round(l, 2), Math.Round(c, 2),
                crng.NextInt64(5_000, 150_000), t));
            price = c;
        }
        return Task.FromResult(candles);
    }

    public Task<TickDto?> GetLatestTickAsync(string symbol)
    {
        var price = StablePrice(symbol);
        return Task.FromResult<TickDto?>(
            new TickDto(symbol, price, 123_456, price - 0.5m, price + 0.5m, DateTime.UtcNow));
    }
}

// ── Options Chain ────────────────────────────────────────────────────────────
public class MockOptionsService : IOptionsService
{
    private static readonly Dictionary<string, decimal> _spotPrices = new()
    {
        ["NIFTY"] = 24502.55m, ["BANKNIFTY"] = 51486.40m,
        ["FINNIFTY"] = 23812.80m, ["MIDCPNIFTY"] = 12204.55m,
    };
    private static readonly Dictionary<string, decimal> _strikeIntervals = new()
    {
        ["NIFTY"] = 50m, ["BANKNIFTY"] = 100m, ["FINNIFTY"] = 50m, ["MIDCPNIFTY"] = 25m,
    };

    public Task<List<string>> GetOptionableSymbolsAsync() =>
        Task.FromResult(new List<string> { "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY" });

    public Task<List<OptionsExpiryDto>> GetExpiriesAsync(string symbol)
    {
        var expiries = new List<OptionsExpiryDto>();
        var today    = DateTime.Today;
        // 4 weekly expiries
        var cur = today;
        for (int i = 0; i < 4; i++)
        {
            cur = NextThursday(cur.AddDays(i == 0 ? 0 : 1));
            expiries.Add(new OptionsExpiryDto(cur.ToString("yyyy-MM-dd"), cur.ToString("dd MMM''yy"), "weekly"));
            cur = cur.AddDays(1);
        }
        // 2 monthly expiries (last Thursday of next 2 months)
        for (int m = 1; m <= 2; m++)
        {
            var month = new DateTime(today.Year, today.Month, 1).AddMonths(m);
            var lastDay = new DateTime(month.Year, month.Month, DateTime.DaysInMonth(month.Year, month.Month));
            while (lastDay.DayOfWeek != DayOfWeek.Thursday) lastDay = lastDay.AddDays(-1);
            if (!expiries.Any(e => e.Expiry == lastDay.ToString("yyyy-MM-dd")))
                expiries.Add(new OptionsExpiryDto(lastDay.ToString("yyyy-MM-dd"), lastDay.ToString("dd MMM''yy") + " (Monthly)", "monthly"));
        }
        return Task.FromResult(expiries);
    }

    public Task<OptionsChainDto> GetOptionsChainAsync(string symbol, string expiry)
    {
        var baseSpot  = _spotPrices.GetValueOrDefault(symbol, 24500m);
        var interval  = _strikeIntervals.GetValueOrDefault(symbol, 50m);
        // Small stable jitter on spot
        var spotSeed  = (symbol + DateTime.UtcNow.ToString("yyyyMMddHHmm")).GetHashCode();
        var spotRng   = new Random(spotSeed);
        var spot      = baseSpot + (decimal)(spotRng.NextDouble() * (double)interval * 0.6 - (double)interval * 0.3);
        spot          = Math.Round(spot, 2);
        var atmStrike = Math.Round(spot / interval) * interval;
        var expiryDate = DateTime.TryParse(expiry, out var ed) ? ed : DateTime.Today.AddDays(7);
        var daysToExpiry = Math.Max(1, (expiryDate - DateTime.Today).Days);
        var t = daysToExpiry / 365.0;

        var rows = new List<OptionsChainRowDto>();
        for (var strike = atmStrike - interval * 30; strike <= atmStrike + interval * 30; strike += interval)
            rows.Add(GenerateRow(symbol, expiry, spot, strike, atmStrike, t));

        return Task.FromResult(new OptionsChainDto(symbol, spot, expiry, atmStrike, rows));
    }

    private static OptionsChainRowDto GenerateRow(string symbol, string expiry, decimal spot, decimal strike, decimal atmStrike, double t)
    {
        var seed = (symbol + expiry + strike.ToString()).GetHashCode();
        var rng  = new Random(seed);
        var sqrtT = Math.Sqrt(t);
        var r = 0.065;
        var moneyness = Math.Log((double)spot / (double)strike);

        // IV smile: puts OTM have higher IV (put skew)
        var atmIv = 0.15 + (double)Math.Abs(strike - atmStrike) / (double)atmStrike * 2.0;
        var ceIv  = atmIv + Math.Max(0, -moneyness) * 0.05;
        var peIv  = atmIv + Math.Max(0,  moneyness) * 0.10 + 0.01;

        double CeDelta, PeDelta, Gamma, CeTheta, PeTheta, Vega, CeLtp, PeLtp;
        ComputeBS((double)spot, (double)strike, t, r, ceIv, peIv, sqrtT,
            out CeDelta, out PeDelta, out Gamma, out CeTheta, out PeTheta, out Vega, out CeLtp, out PeLtp);

        // OI: peak at ATM
        var dist = Math.Abs((double)(strike - atmStrike) / (double)atmStrike);
        var oiBase = (long)(8_00_000 * Math.Exp(-dist * 18));
        var ceOi = oiBase + rng.NextInt64(0, Math.Max(1, oiBase / 8));
        var peOi = (long)(oiBase * 1.15) + rng.NextInt64(0, Math.Max(1, oiBase / 8));
        var ceOiChg = (long)(rng.NextInt64(-200_000, 400_000));
        var peOiChg = (long)(rng.NextInt64(-200_000, 400_000));
        var ceVol = ceOi / 12 + rng.NextInt64(0, 5000);
        var peVol = peOi / 12 + rng.NextInt64(0, 5000);
        var ceChg = (decimal)Math.Round(rng.NextDouble() * 30 - 10, 2);
        var peChg = (decimal)Math.Round(rng.NextDouble() * 30 - 10, 2);
        var ltpCe = Math.Max(0.05m, Math.Round((decimal)CeLtp, 2));
        var ltpPe = Math.Max(0.05m, Math.Round((decimal)PeLtp, 2));

        var ce = new OptionLegDto(ceOi, ceOiChg, ceVol, Math.Round(ceIv * 100, 2), ltpCe, ceChg,
            rng.NextInt64(50, 3000), Math.Max(0.05m, ltpCe - 0.5m), ltpCe + 0.5m, rng.NextInt64(50, 3000),
            Math.Round((decimal)CeDelta, 4), Math.Round((decimal)Gamma, 6),
            Math.Round((decimal)CeTheta, 2), Math.Round((decimal)Vega, 2));
        var pe = new OptionLegDto(peOi, peOiChg, peVol, Math.Round(peIv * 100, 2), ltpPe, peChg,
            rng.NextInt64(50, 3000), Math.Max(0.05m, ltpPe - 0.5m), ltpPe + 0.5m, rng.NextInt64(50, 3000),
            Math.Round((decimal)PeDelta, 4), Math.Round((decimal)Gamma, 6),
            Math.Round((decimal)PeTheta, 2), Math.Round((decimal)Vega, 2));

        return new OptionsChainRowDto(strike, strike == atmStrike, strike < spot, strike > spot, ce, pe);
    }

    private static void ComputeBS(double S, double K, double T, double r, double ceIv, double peIv, double sqrtT,
        out double CeDelta, out double PeDelta, out double Gamma, out double CeTheta, out double PeTheta, out double Vega,
        out double CeLtp, out double PeLtp)
    {
        var d1c = (Math.Log(S / K) + (r + ceIv * ceIv / 2) * T) / (ceIv * sqrtT);
        var d2c = d1c - ceIv * sqrtT;
        var d1p = (Math.Log(S / K) + (r + peIv * peIv / 2) * T) / (peIv * sqrtT);
        var d2p = d1p - peIv * sqrtT;
        CeDelta = Ncdf(d1c);
        PeDelta = Ncdf(d1p) - 1.0;
        Gamma   = Npdf(d1c) / (S * ceIv * sqrtT);
        var expRt = Math.Exp(-r * T);
        CeLtp   = S * Ncdf(d1c) - K * expRt * Ncdf(d2c);
        PeLtp   = K * expRt * Ncdf(-d2p) - S * Ncdf(-d1p);
        CeTheta = -(S * Npdf(d1c) * ceIv) / (2 * sqrtT * 365) - r * K * expRt * Ncdf(d2c) / 365;
        PeTheta = -(S * Npdf(d1p) * peIv) / (2 * sqrtT * 365) + r * K * expRt * Ncdf(-d2p) / 365;
        Vega    = S * Npdf(d1c) * sqrtT * 0.01;
        CeLtp   = Math.Max(Math.Max(0, S - K), CeLtp);
        PeLtp   = Math.Max(Math.Max(0, K - S), PeLtp);
    }

    private static double Ncdf(double x)
    {
        const double a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
        const double a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
        int sign = x < 0 ? -1 : 1;
        x = Math.Abs(x) / Math.Sqrt(2.0);
        var t = 1.0 / (1.0 + p * x);
        var y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.Exp(-x * x));
        return 0.5 * (1.0 + sign * y);
    }
    private static double Npdf(double x) => Math.Exp(-0.5 * x * x) / Math.Sqrt(2 * Math.PI);

    private static DateTime NextThursday(DateTime from)
    {
        int days = ((int)DayOfWeek.Thursday - (int)from.DayOfWeek + 7) % 7;
        return from.AddDays(days == 0 ? 7 : days);
    }
}

// ── AI Predictions ────────────────────────────────────────────────────────────
public class MockPredictionService : IPredictionService
{
    public Task<List<PredictionDto>> GetPredictionsAsync() => Task.FromResult(new List<PredictionDto>
    {
        new("NIFTY",      "BUY",  "CE",    24600m, "2026-06-05", 0.87, "BULLISH",  24850m, 24400m, "1D",      8.2, 2.5, "RSI oversold recovery + EMA crossover. Heavy CE OI buildup at 24500.", DateTime.UtcNow),
        new("BANKNIFTY",  "SELL", "PE",    51000m, "2026-06-05", 0.78, "BEARISH",  50750m, 51600m, "INTRADAY",4.5, 1.8, "Bearish engulfing on 15m. BANKNIFTY underperforming NIFTY. High PE OI at 51500.", DateTime.UtcNow),
        new("RELIANCE",   "BUY",  "STOCK", 0m,     "",           0.74, "TRENDING", 3050m,  2940m,  "1D",      5.2, 1.6, "Breakout above resistance. High volume confirmation. Energy sector rotation.", DateTime.UtcNow),
        new("NIFTY",      "BUY",  "CE",    24700m, "2026-06-05", 0.71, "BULLISH",  24950m, 24500m, "1W",      7.1, 2.2, "Weekly trend continuation. ATR expanding. 50-period MA acting as support.", DateTime.UtcNow),
        new("INFY",       "SELL", "PE",    1550m,  "2026-06-05", 0.68, "BEARISH",  1490m,  1610m,  "1D",      6.3, 1.9, "Head and shoulders pattern forming. IT sector weakness. RSI divergence.", DateTime.UtcNow),
        new("BANKNIFTY",  "BUY",  "CE",    52000m, "2026-06-05", 0.65, "RANGING",  52400m, 51600m, "INTRADAY",3.8, 1.5, "Support at 51500 holding. Stochastic RSI crossing up in oversold zone.", DateTime.UtcNow),
        new("TCS",        "BUY",  "STOCK", 0m,     "",           0.63, "TRENDING", 4150m,  3950m,  "1W",      4.2, 1.4, "Channel breakout with volume. Q4 results beat. IT sector recovery.", DateTime.UtcNow),
        new("HDFCBANK",   "SELL", "PE",    1700m,  "2026-06-05", 0.61, "BEARISH",  1650m,  1755m,  "1D",      3.5, 1.3, "Double top at 1750. Banking index weakness. FII outflow pressure.", DateTime.UtcNow),
    });
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
