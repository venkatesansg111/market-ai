using Trading.Contracts;

namespace Trading.Domain;

public interface IPortfolioService
{
    Task<PortfolioDto> GetPortfolioAsync();
    Task<PortfolioHistoryDto> GetHistoryAsync(int days = 30);
    Task<ExposureDto> GetExposureAsync();
    Task<List<PositionDto>> GetPositionsAsync();
    Task<PositionDto?> GetPositionAsync(string symbol);
}

public interface IOrderService
{
    Task<List<OrderDto>> GetOrdersAsync(string? status = null, string? symbol = null);
    Task<OrderDto?> GetOrderAsync(string orderId);
    Task<bool> CancelOrderAsync(string orderId);
    Task<List<TradeDto>> GetTradesAsync(string? symbol = null, string? strategy = null);
    Task<TradeDto?> GetTradeAsync(string tradeId);
}

public interface IStrategyService
{
    Task<List<StrategyDto>> GetStrategiesAsync();
    Task<List<StrategyDto>> GetPerformanceAsync();
    Task<List<RegimeTimelineDto>> GetRegimesAsync();
    Task<bool> EnableStrategyAsync(string name);
    Task<bool> DisableStrategyAsync(string name);
}

public interface IRiskService
{
    Task<RiskDto> GetRiskAsync();
    Task<ExposureDto> GetExposureAsync();
    Task<List<RiskAlertDto>> GetAlertsAsync();
    Task<bool> UpdateRiskLimitsAsync(string limitType, decimal value);
}

public interface IExplainabilityService
{
    Task<TradeExplanationDto?> ExplainTradeAsync(string tradeId);
    Task<List<TradeExplanationDto>> ExplainAllTradesAsync();
}

public interface IReplayService
{
    Task<ReplayStatusDto> GetStatusAsync();
    Task<bool> StartAsync(double speed = 1.0);
    Task<bool> PauseAsync();
    Task<bool> StopAsync();
}

public interface ISystemHealthService
{
    Task<SystemHealthDto> GetHealthAsync();
}

public interface IAlertService
{
    Task<List<AlertDto>> GetAlertsAsync(string? severity = null, string? category = null);
    Task<bool> AcknowledgeAlertAsync(string alertId);
}

public interface IMarketDataService
{
    Task<List<WatchlistItemDto>> GetWatchlistAsync(string exchange = "NSE");
    Task<List<CandleDto>> GetCandlesAsync(string symbol, string timeframe, int limit = 100);
    Task<TickDto?> GetLatestTickAsync(string symbol);
}

public interface IPnLAttributionService
{
    Task<PnLAttributionDto> GetAttributionAsync();
}

public interface IAdminService
{
    Task<AdminActionResponse> ExecuteActionAsync(AdminActionRequest request);
    Task<bool> PauseTradingAsync();
    Task<bool> ResumeTradingAsync();
    Task<bool> KillSwitchAsync();
}

public interface IAuthService
{
    Task<LoginResponse?> LoginAsync(LoginRequest request);
    bool ValidateToken(string token);
}

public interface IAuditService
{
    Task LogActionAsync(string userId, string action, string details);
    Task<List<AuditLogEntry>> GetLogsAsync(int limit = 100);
}

public record AuditLogEntry(
    string Id,
    string UserId,
    string Action,
    string Details,
    DateTime Timestamp
);
