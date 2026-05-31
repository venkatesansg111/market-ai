using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/options")]
[Authorize]
public class OptionsController(IOptionsService options) : ControllerBase
{
    [HttpGet("symbols")]
    public async Task<IActionResult> GetSymbols() =>
        Ok(await options.GetOptionableSymbolsAsync());

    [HttpGet("expiries")]
    public async Task<IActionResult> GetExpiries([FromQuery] string symbol = "NIFTY") =>
        Ok(await options.GetExpiriesAsync(symbol));

    [HttpGet("chain")]
    public async Task<IActionResult> GetChain(
        [FromQuery] string symbol = "NIFTY",
        [FromQuery] string? expiry = null)
    {
        if (expiry == null)
        {
            var expiries = await options.GetExpiriesAsync(symbol);
            expiry = expiries.FirstOrDefault()?.Expiry ?? DateTime.Today.AddDays(7).ToString("yyyy-MM-dd");
        }
        return Ok(await options.GetOptionsChainAsync(symbol, expiry));
    }
}
