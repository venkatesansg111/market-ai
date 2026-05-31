using Microsoft.AspNetCore.Mvc;
using Trading.Contracts;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class AuthController : ControllerBase
{
    private readonly IAuthService _auth;

    public AuthController(IAuthService auth) => _auth = auth;

    [HttpPost("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var result = await _auth.LoginAsync(request);
        if (result is null) return Unauthorized(new { message = "Invalid credentials" });
        return Ok(result);
    }

    [HttpGet("me")]
    [Microsoft.AspNetCore.Authorization.Authorize]
    public IActionResult Me()
    {
        var name = User.Identity?.Name ?? "unknown";
        var role = User.Claims.FirstOrDefault(c => c.Type == System.Security.Claims.ClaimTypes.Role)?.Value ?? "unknown";
        return Ok(new { username = name, role });
    }
}
