using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class OrdersController : ControllerBase
{
    private readonly IOrderService _orders;

    public OrdersController(IOrderService orders) => _orders = orders;

    [HttpGet]
    public async Task<IActionResult> GetAll([FromQuery] string? status, [FromQuery] string? symbol) =>
        Ok(await _orders.GetOrdersAsync(status, symbol));

    [HttpGet("{id}")]
    public async Task<IActionResult> GetById(string id)
    {
        var o = await _orders.GetOrderAsync(id);
        return o is null ? NotFound() : Ok(o);
    }

    [HttpPost("{id}/cancel")]
    [Authorize(Roles = "Admin,Trader")]
    public async Task<IActionResult> Cancel(string id) =>
        Ok(new { success = await _orders.CancelOrderAsync(id) });
}
