using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class RiskController : ControllerBase
{
    private readonly IRiskService _risk;

    public RiskController(IRiskService risk) => _risk = risk;

    [HttpGet]
    public async Task<IActionResult> Get() => Ok(await _risk.GetRiskAsync());

    [HttpGet("exposure")]
    public async Task<IActionResult> Exposure() => Ok(await _risk.GetExposureAsync());

    [HttpGet("alerts")]
    public async Task<IActionResult> Alerts() => Ok(await _risk.GetAlertsAsync());
}
