using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class StrategiesController : ControllerBase
{
    private readonly IStrategyService _strategies;

    public StrategiesController(IStrategyService strategies) => _strategies = strategies;

    [HttpGet]
    public async Task<IActionResult> GetAll() => Ok(await _strategies.GetStrategiesAsync());

    [HttpGet("performance")]
    public async Task<IActionResult> Performance() => Ok(await _strategies.GetPerformanceAsync());

    [HttpGet("regimes")]
    public async Task<IActionResult> Regimes() => Ok(await _strategies.GetRegimesAsync());
}
