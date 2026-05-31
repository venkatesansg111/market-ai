using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize(Roles = "Admin,Trader,Researcher")]
public class ReplayController : ControllerBase
{
    private readonly IReplayService _replay;

    public ReplayController(IReplayService replay) => _replay = replay;

    [HttpGet("status")]
    public async Task<IActionResult> Status() => Ok(await _replay.GetStatusAsync());

    [HttpPost("start")]
    public async Task<IActionResult> Start([FromQuery] double speed = 1.0) =>
        Ok(new { success = await _replay.StartAsync(speed) });

    [HttpPost("pause")]
    public async Task<IActionResult> Pause() =>
        Ok(new { success = await _replay.PauseAsync() });

    [HttpPost("stop")]
    public async Task<IActionResult> Stop() =>
        Ok(new { success = await _replay.StopAsync() });
}
