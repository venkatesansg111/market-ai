using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class PortfolioController : ControllerBase
{
    private readonly IPortfolioService _portfolio;

    public PortfolioController(IPortfolioService portfolio) => _portfolio = portfolio;

    [HttpGet]
    public async Task<IActionResult> Get() => Ok(await _portfolio.GetPortfolioAsync());

    [HttpGet("history")]
    public async Task<IActionResult> History([FromQuery] int days = 30) =>
        Ok(await _portfolio.GetHistoryAsync(days));

    [HttpGet("exposure")]
    public async Task<IActionResult> Exposure() => Ok(await _portfolio.GetExposureAsync());
}
