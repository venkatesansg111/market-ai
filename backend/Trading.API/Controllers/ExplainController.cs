using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class ExplainController : ControllerBase
{
    private readonly IExplainabilityService _explain;

    public ExplainController(IExplainabilityService explain) => _explain = explain;

    [HttpGet("trade/{tradeId}")]
    public async Task<IActionResult> ExplainTrade(string tradeId)
    {
        var result = await _explain.ExplainTradeAsync(tradeId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpGet("trades")]
    public async Task<IActionResult> ExplainAll() => Ok(await _explain.ExplainAllTradesAsync());
}
