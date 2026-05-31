using Trading.Infrastructure;
using Xunit;

namespace Trading.API.Tests;

public class MockPortfolioServiceTests
{
    [Fact]
    public async Task GetPortfolio_ReturnsNonNullEquity()
    {
        var svc = new MockPortfolioService();
        var p = await svc.GetPortfolioAsync();
        Assert.True(p.Equity > 0);
        Assert.True(p.Cash > 0);
    }

    [Fact]
    public async Task GetPositions_ReturnsNonEmptyList()
    {
        var svc = new MockPortfolioService();
        var positions = await svc.GetPositionsAsync();
        Assert.NotEmpty(positions);
    }

    [Fact]
    public async Task GetPosition_ExistingSymbol_ReturnsPosition()
    {
        var svc = new MockPortfolioService();
        var pos = await svc.GetPositionAsync("RELIANCE");
        Assert.NotNull(pos);
        Assert.Equal("RELIANCE", pos.Symbol);
    }

    [Fact]
    public async Task GetPosition_UnknownSymbol_ReturnsNull()
    {
        var svc = new MockPortfolioService();
        var pos = await svc.GetPositionAsync("UNKNOWNSYMBOL");
        Assert.Null(pos);
    }

    [Fact]
    public async Task GetHistory_ReturnsEquityCurve()
    {
        var svc = new MockPortfolioService();
        var hist = await svc.GetHistoryAsync(30);
        Assert.NotEmpty(hist.EquityCurve);
        Assert.NotEmpty(hist.DrawdownCurve);
    }

    [Fact]
    public async Task GetExposure_ReturnsSymbolExposure()
    {
        var svc = new MockPortfolioService();
        var exp = await svc.GetExposureAsync();
        Assert.NotEmpty(exp.BySymbol);
        Assert.NotEmpty(exp.ByStrategy);
    }
}

public class MockOrderServiceTests
{
    [Fact]
    public async Task GetOrders_NoFilter_ReturnsAllOrders()
    {
        var svc = new MockOrderService();
        var orders = await svc.GetOrdersAsync();
        Assert.NotEmpty(orders);
    }

    [Fact]
    public async Task GetOrders_FilterByStatus_ReturnsFilled()
    {
        var svc = new MockOrderService();
        var orders = await svc.GetOrdersAsync(status: "FILLED");
        Assert.All(orders, o => Assert.Equal("FILLED", o.Status));
    }

    [Fact]
    public async Task GetOrder_ExistingId_ReturnsOrder()
    {
        var svc = new MockOrderService();
        var o = await svc.GetOrderAsync("ORD-001");
        Assert.NotNull(o);
    }

    [Fact]
    public async Task GetOrder_UnknownId_ReturnsNull()
    {
        var svc = new MockOrderService();
        var o = await svc.GetOrderAsync("UNKNOWN");
        Assert.Null(o);
    }

    [Fact]
    public async Task GetTrades_ReturnsNonEmpty()
    {
        var svc = new MockOrderService();
        var trades = await svc.GetTradesAsync();
        Assert.NotEmpty(trades);
    }

    [Fact]
    public async Task CancelOrder_ReturnsTrue()
    {
        var svc = new MockOrderService();
        var result = await svc.CancelOrderAsync("ORD-005");
        Assert.True(result);
    }
}

public class MockStrategyServiceTests
{
    [Fact]
    public async Task GetStrategies_ReturnsStrategies()
    {
        var svc = new MockStrategyService();
        var strategies = await svc.GetStrategiesAsync();
        Assert.NotEmpty(strategies);
    }

    [Fact]
    public async Task GetRegimes_ReturnsTimelines()
    {
        var svc = new MockStrategyService();
        var regimes = await svc.GetRegimesAsync();
        Assert.NotEmpty(regimes);
    }

    [Fact]
    public async Task EnableStrategy_ReturnsTrue()
    {
        var svc = new MockStrategyService();
        Assert.True(await svc.EnableStrategyAsync("momentum"));
    }

    [Fact]
    public async Task DisableStrategy_ReturnsTrue()
    {
        var svc = new MockStrategyService();
        Assert.True(await svc.DisableStrategyAsync("volatility_arb"));
    }
}

public class MockRiskServiceTests
{
    [Fact]
    public async Task GetRisk_ReturnsRiskDto()
    {
        var svc = new MockRiskService();
        var risk = await svc.GetRiskAsync();
        Assert.False(risk.TradingHalted);
        Assert.True(risk.TotalExposure > 0);
    }

    [Fact]
    public async Task GetAlerts_ReturnsAlerts()
    {
        var svc = new MockRiskService();
        var alerts = await svc.GetAlertsAsync();
        Assert.NotEmpty(alerts);
    }
}

public class MockSystemHealthServiceTests
{
    [Fact]
    public async Task GetHealth_ReturnsHealthy()
    {
        var svc = new MockSystemHealthService();
        var health = await svc.GetHealthAsync();
        Assert.Equal("healthy", health.Status);
        Assert.True(health.PublishCount > 0);
    }
}

public class MockAlertServiceTests
{
    [Fact]
    public async Task GetAlerts_NoFilter_ReturnsAll()
    {
        var svc = new MockAlertService();
        var alerts = await svc.GetAlertsAsync();
        Assert.NotEmpty(alerts);
    }

    [Fact]
    public async Task GetAlerts_FilterBySeverity_ReturnsFiltered()
    {
        var svc = new MockAlertService();
        var warnings = await svc.GetAlertsAsync(severity: "WARNING");
        Assert.All(warnings, a => Assert.Equal("WARNING", a.Severity));
    }

    [Fact]
    public async Task Acknowledge_ExistingAlert_ReturnsTrue()
    {
        var svc = new MockAlertService();
        Assert.True(await svc.AcknowledgeAlertAsync("ALT-001"));
    }
}

public class MockMarketDataServiceTests
{
    [Fact]
    public async Task GetWatchlist_NSE_ReturnsItems()
    {
        var svc = new MockMarketDataService();
        var items = await svc.GetWatchlistAsync("NSE");
        Assert.NotEmpty(items);
    }

    [Fact]
    public async Task GetCandles_ReturnsCandles()
    {
        var svc = new MockMarketDataService();
        var candles = await svc.GetCandlesAsync("RELIANCE", "1m", 50);
        Assert.Equal(51, candles.Count);
    }

    [Fact]
    public async Task GetTick_ReturnsTickDto()
    {
        var svc = new MockMarketDataService();
        var tick = await svc.GetLatestTickAsync("RELIANCE");
        Assert.NotNull(tick);
    }
}

public class MockExplainabilityServiceTests
{
    [Fact]
    public async Task ExplainTrade_Known_ReturnsExplanation()
    {
        var svc = new MockExplainabilityService();
        var exp = await svc.ExplainTradeAsync("TRD-001");
        Assert.NotNull(exp);
        Assert.NotEmpty(exp.DecisionChain);
        Assert.Equal("RELIANCE", exp.Symbol);
    }

    [Fact]
    public async Task ExplainTrade_Unknown_ReturnsNull()
    {
        var svc = new MockExplainabilityService();
        Assert.Null(await svc.ExplainTradeAsync("UNKNOWN"));
    }
}

public class MockPnLAttributionServiceTests
{
    [Fact]
    public async Task GetAttribution_ReturnsPositiveTotalPnL()
    {
        var svc = new MockPnLAttributionService();
        var attr = await svc.GetAttributionAsync();
        Assert.True(attr.TotalPnl > 0);
        Assert.NotEmpty(attr.ByStrategy);
        Assert.NotEmpty(attr.ByAsset);
    }
}
