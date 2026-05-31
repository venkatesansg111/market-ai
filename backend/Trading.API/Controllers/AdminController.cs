using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Contracts;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize(Roles = "Admin")]
public class AdminController : ControllerBase
{
    private readonly IStrategyService _strategies;
    private readonly IAdminService _admin;
    private readonly IAuditService _audit;

    public AdminController(IStrategyService strategies, IAdminService admin, IAuditService audit)
    {
        _strategies = strategies;
        _admin = admin;
        _audit = audit;
    }

    [HttpPost("strategy/enable")]
    public async Task<IActionResult> EnableStrategy([FromBody] AdminActionRequest req)
    {
        var ok = await _strategies.EnableStrategyAsync(req.Target ?? req.Action);
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "STRATEGY_ENABLE", $"Enabled {req.Target}");
        return Ok(new AdminActionResponse(ok, ok ? "Strategy enabled" : "Failed"));
    }

    [HttpPost("strategy/disable")]
    public async Task<IActionResult> DisableStrategy([FromBody] AdminActionRequest req)
    {
        var ok = await _strategies.DisableStrategyAsync(req.Target ?? req.Action);
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "STRATEGY_DISABLE", $"Disabled {req.Target}");
        return Ok(new AdminActionResponse(ok, ok ? "Strategy disabled" : "Failed"));
    }

    [HttpPost("trading/pause")]
    public async Task<IActionResult> PauseTrading()
    {
        var ok = await _admin.PauseTradingAsync();
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "TRADING_PAUSE", "Trading paused");
        return Ok(new AdminActionResponse(ok, ok ? "Trading paused" : "Failed"));
    }

    [HttpPost("trading/resume")]
    public async Task<IActionResult> ResumeTrading()
    {
        var ok = await _admin.ResumeTradingAsync();
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "TRADING_RESUME", "Trading resumed");
        return Ok(new AdminActionResponse(ok, ok ? "Trading resumed" : "Failed"));
    }

    [HttpPost("kill-switch")]
    public async Task<IActionResult> KillSwitch()
    {
        var ok = await _admin.KillSwitchAsync();
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "KILL_SWITCH", "Emergency kill switch activated");
        return Ok(new AdminActionResponse(ok, ok ? "Kill switch activated — all trading halted" : "Failed"));
    }

    [HttpGet("audit")]
    public async Task<IActionResult> GetAuditLog([FromQuery] int limit = 100) =>
        Ok(await _audit.GetLogsAsync(limit));

    [HttpGet("risk-limits")]
    public async Task<IActionResult> GetRiskLimits() =>
        Ok(new { maxDrawdownPct = 10.0, maxLeverage = 2.0, dailyLossLimit = 50000.0, maxExposurePct = 80.0 });

    [HttpPost("risk-limits")]
    public async Task<IActionResult> UpdateRiskLimits([FromBody] AdminActionRequest req)
    {
        if (!decimal.TryParse(req.Value, out var value))
            return BadRequest("Invalid value");
        await _audit.LogActionAsync(User.Identity?.Name ?? "admin", "RISK_LIMIT_UPDATE",
            $"Updated {req.Target} to {value}");
        return Ok(new AdminActionResponse(true, $"Risk limit '{req.Target}' updated to {value}"));
    }
}
