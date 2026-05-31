using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Trading.Contracts;
using Trading.Domain;

namespace Trading.API.Hubs;

[Authorize]
public class TradingHub : Hub
{
    private readonly IPortfolioService _portfolio;
    private readonly ISystemHealthService _health;
    private readonly IAlertService _alerts;

    public TradingHub(IPortfolioService portfolio, ISystemHealthService health, IAlertService alerts)
    {
        _portfolio = portfolio;
        _health = health;
        _alerts = alerts;
    }

    public override async Task OnConnectedAsync()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "trading");
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? ex)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, "trading");
        await base.OnDisconnectedAsync(ex);
    }

    public async Task SubscribePortfolio()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "portfolio");
        var snapshot = await _portfolio.GetPortfolioAsync();
        await Clients.Caller.SendAsync("PortfolioUpdate", snapshot);
    }

    public async Task SubscribeHealth()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "health");
        var snapshot = await _health.GetHealthAsync();
        await Clients.Caller.SendAsync("HealthUpdate", snapshot);
    }

    public async Task SubscribeAlerts()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "alerts");
        var active = await _alerts.GetAlertsAsync();
        await Clients.Caller.SendAsync("AlertsSnapshot", active);
    }

    public async Task SubscribeMarket(string symbol)
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, $"market-{symbol}");
    }

    public async Task UnsubscribeMarket(string symbol)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"market-{symbol}");
    }

    public async Task Ping() => await Clients.Caller.SendAsync("Pong", DateTime.UtcNow);
}
