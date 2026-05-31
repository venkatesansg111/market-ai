using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class AlertsController : ControllerBase
{
    private readonly IAlertService _alerts;

    public AlertsController(IAlertService alerts) => _alerts = alerts;

    [HttpGet]
    public async Task<IActionResult> GetAll([FromQuery] string? severity, [FromQuery] string? category) =>
        Ok(await _alerts.GetAlertsAsync(severity, category));

    [HttpPost("{alertId}/acknowledge")]
    public async Task<IActionResult> Acknowledge(string alertId) =>
        Ok(new { success = await _alerts.AcknowledgeAlertAsync(alertId) });
}
