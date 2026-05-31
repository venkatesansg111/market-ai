using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/pnl")]
[Authorize]
public class PnLController : ControllerBase
{
    private readonly IPnLAttributionService _pnl;

    public PnLController(IPnLAttributionService pnl) => _pnl = pnl;

    [HttpGet("attribution")]
    public async Task<IActionResult> Attribution() => Ok(await _pnl.GetAttributionAsync());
}
