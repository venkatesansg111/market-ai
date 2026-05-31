using Microsoft.Extensions.Configuration;
using Trading.Application.Services;
using Trading.Contracts;
using Xunit;

namespace Trading.Application.Tests;

public class JwtServiceTests
{
    private static JwtService CreateService()
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Jwt:Key"]      = "trading-terminal-super-secret-key-32chars!!",
                ["Jwt:Issuer"]   = "TradingTerminal",
                ["Jwt:Audience"] = "TradingTerminalUsers",
            })
            .Build();
        return new JwtService(config);
    }

    [Fact]
    public async Task Login_ValidAdmin_ReturnsToken()
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest("admin", "admin123"));
        Assert.NotNull(result);
        Assert.Equal("Admin", result.Role);
        Assert.NotEmpty(result.Token);
    }

    [Fact]
    public async Task Login_InvalidPassword_ReturnsNull()
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest("admin", "wrongpassword"));
        Assert.Null(result);
    }

    [Fact]
    public async Task Login_UnknownUser_ReturnsNull()
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest("nobody", "pass"));
        Assert.Null(result);
    }

    [Theory]
    [InlineData("trader",     "trader123",   "Trader")]
    [InlineData("viewer",     "viewer123",   "Viewer")]
    [InlineData("researcher", "research123", "Researcher")]
    public async Task Login_AllRoles_ReturnCorrectRole(string user, string pass, string role)
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest(user, pass));
        Assert.NotNull(result);
        Assert.Equal(role, result.Role);
    }

    [Fact]
    public async Task Token_Expiry_IsFutureDate()
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest("admin", "admin123"));
        Assert.NotNull(result);
        Assert.True(result.ExpiresAt > DateTime.UtcNow);
    }

    [Fact]
    public async Task ValidateToken_ValidToken_ReturnsTrue()
    {
        var svc = CreateService();
        var result = await svc.LoginAsync(new LoginRequest("admin", "admin123"));
        Assert.NotNull(result);
        Assert.True(svc.ValidateToken(result.Token));
    }

    [Fact]
    public void ValidateToken_InvalidToken_ReturnsFalse()
    {
        var svc = CreateService();
        Assert.False(svc.ValidateToken("this.is.not.valid"));
    }
}
