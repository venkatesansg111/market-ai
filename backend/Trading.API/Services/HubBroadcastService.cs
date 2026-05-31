using Microsoft.AspNetCore.SignalR;
using Trading.API.Hubs;
using Trading.Domain;

namespace Trading.API.Services;

/// <summary>
/// Background service that periodically broadcasts live updates to connected SignalR clients.
/// </summary>
public class HubBroadcastService : BackgroundService
{
    private readonly IHubContext<TradingHub> _hub;
    private readonly IServiceProvider _services;
    private readonly ILogger<HubBroadcastService> _logger;

    public HubBroadcastService(IHubContext<TradingHub> hub, IServiceProvider services, ILogger<HubBroadcastService> logger)
    {
        _hub = hub;
        _services = services;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await using var scope = _services.CreateAsyncScope();
                var portfolio = scope.ServiceProvider.GetRequiredService<IPortfolioService>();
                var health    = scope.ServiceProvider.GetRequiredService<ISystemHealthService>();
                var alerts    = scope.ServiceProvider.GetRequiredService<IAlertService>();
                var positions = scope.ServiceProvider.GetRequiredService<IPortfolioService>();

                var portfolioSnap = await portfolio.GetPortfolioAsync();
                var healthSnap    = await health.GetHealthAsync();
                var activeAlerts  = await alerts.GetAlertsAsync(severity: null);
                var positionList  = await positions.GetPositionsAsync();

                await _hub.Clients.Group("portfolio").SendAsync("PortfolioUpdate", portfolioSnap, stoppingToken);
                await _hub.Clients.Group("health").SendAsync("HealthUpdate", healthSnap, stoppingToken);
                await _hub.Clients.Group("alerts").SendAsync("AlertsUpdate", activeAlerts, stoppingToken);
                await _hub.Clients.All.SendAsync("PositionsUpdate", positionList, stoppingToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error broadcasting hub updates");
            }

            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }
}
