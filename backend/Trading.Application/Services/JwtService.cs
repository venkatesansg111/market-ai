using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using Trading.Contracts;
using Trading.Domain;

namespace Trading.Application.Services;

public class JwtService : IAuthService
{
    private readonly IConfiguration _config;

    private static readonly Dictionary<string, (string Password, string Role)> _users = new()
    {
        ["admin"]      = ("admin123",    "Admin"),
        ["trader"]     = ("trader123",   "Trader"),
        ["viewer"]     = ("viewer123",   "Viewer"),
        ["researcher"] = ("research123", "Researcher"),
    };

    public JwtService(IConfiguration config) => _config = config;

    public Task<LoginResponse?> LoginAsync(LoginRequest request)
    {
        if (!_users.TryGetValue(request.Username, out var creds) || creds.Password != request.Password)
            return Task.FromResult<LoginResponse?>(null);

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_config["Jwt:Key"]!));
        var cred = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var expires = DateTime.UtcNow.AddHours(8);

        var claims = new[]
        {
            new Claim(ClaimTypes.Name, request.Username),
            new Claim(ClaimTypes.Role, creds.Role),
            new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
        };

        var token = new JwtSecurityToken(
            issuer: _config["Jwt:Issuer"],
            audience: _config["Jwt:Audience"],
            claims: claims,
            expires: expires,
            signingCredentials: cred
        );

        var tokenStr = new JwtSecurityTokenHandler().WriteToken(token);
        return Task.FromResult<LoginResponse?>(new LoginResponse(tokenStr, creds.Role, request.Username, expires));
    }

    public bool ValidateToken(string token)
    {
        try
        {
            var handler = new JwtSecurityTokenHandler();
            handler.ValidateToken(token, new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_config["Jwt:Key"]!)),
                ValidateIssuer = true,
                ValidIssuer = _config["Jwt:Issuer"],
                ValidateAudience = true,
                ValidAudience = _config["Jwt:Audience"],
                ValidateLifetime = true,
            }, out _);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
