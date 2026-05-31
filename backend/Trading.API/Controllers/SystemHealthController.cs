using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/system-health")]
[Authorize]
public class SystemHealthController : ControllerBase
{
    private readonly ISystemHealthService _health;

    public SystemHealthController(ISystemHealthService health) => _health = health;

    [HttpGet]
    public async Task<IActionResult> Get() => Ok(await _health.GetHealthAsync());
}
