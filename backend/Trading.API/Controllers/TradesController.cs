using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class TradesController : ControllerBase
{
    private readonly IOrderService _orders;

    public TradesController(IOrderService orders) => _orders = orders;

    [HttpGet]
    public async Task<IActionResult> GetAll([FromQuery] string? symbol, [FromQuery] string? strategy) =>
        Ok(await _orders.GetTradesAsync(symbol, strategy));

    [HttpGet("{id}")]
    public async Task<IActionResult> GetById(string id)
    {
        var t = await _orders.GetTradeAsync(id);
        return t is null ? NotFound() : Ok(t);
    }
}
