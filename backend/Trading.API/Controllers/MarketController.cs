using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class MarketController : ControllerBase
{
    private readonly IMarketDataService _market;

    public MarketController(IMarketDataService market) => _market = market;

    [HttpGet("watchlist")]
    public async Task<IActionResult> Watchlist([FromQuery] string exchange = "NSE") =>
        Ok(await _market.GetWatchlistAsync(exchange));

    [HttpGet("candles/{symbol}")]
    public async Task<IActionResult> Candles(string symbol, [FromQuery] string timeframe = "1m", [FromQuery] int limit = 100) =>
        Ok(await _market.GetCandlesAsync(symbol, timeframe, limit));

    [HttpGet("tick/{symbol}")]
    public async Task<IActionResult> Tick(string symbol)
    {
        var tick = await _market.GetLatestTickAsync(symbol);
        return tick is null ? NotFound() : Ok(tick);
    }
}
