using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class PositionsController : ControllerBase
{
    private readonly IPortfolioService _portfolio;

    public PositionsController(IPortfolioService portfolio) => _portfolio = portfolio;

    [HttpGet]
    public async Task<IActionResult> GetAll() => Ok(await _portfolio.GetPositionsAsync());

    [HttpGet("{symbol}")]
    public async Task<IActionResult> GetBySymbol(string symbol)
    {
        var pos = await _portfolio.GetPositionAsync(symbol);
        return pos is null ? NotFound() : Ok(pos);
    }
}
