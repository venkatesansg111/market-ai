using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using Scalar.AspNetCore;
using Trading.API.Hubs;
using Trading.API.Services;
using Trading.Application.Services;
using Trading.Domain;
using Trading.Infrastructure;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddOpenApi();

var jwtKey = builder.Configuration["Jwt:Key"] ?? "trading-terminal-super-secret-key-32chars!!";
var jwtIssuer = builder.Configuration["Jwt:Issuer"] ?? "TradingTerminal";
var jwtAudience = builder.Configuration["Jwt:Audience"] ?? "TradingTerminalUsers";

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtKey)),
            ValidateIssuer = true,
            ValidIssuer = jwtIssuer,
            ValidateAudience = true,
            ValidAudience = jwtAudience,
            ValidateLifetime = true,
        };
        options.Events = new JwtBearerEvents
        {
            OnMessageReceived = context =>
            {
                var accessToken = context.Request.Query["access_token"];
                var path = context.HttpContext.Request.Path;
                if (!string.IsNullOrEmpty(accessToken) && path.StartsWithSegments("/hubs"))
                    context.Token = accessToken;
                return Task.CompletedTask;
            }
        };
    });

builder.Services.AddAuthorization();
builder.Services.AddSignalR();

builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAll", policy =>
        policy.WithOrigins(
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:5174"
              )
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials());
});

// Register domain services
builder.Services.AddScoped<IPortfolioService,       MockPortfolioService>();
builder.Services.AddScoped<IOrderService,           MockOrderService>();
builder.Services.AddScoped<IStrategyService,        MockStrategyService>();
builder.Services.AddScoped<IRiskService,            MockRiskService>();
builder.Services.AddScoped<IExplainabilityService,  MockExplainabilityService>();
builder.Services.AddScoped<IReplayService,          MockReplayService>();
builder.Services.AddScoped<ISystemHealthService,    MockSystemHealthService>();
builder.Services.AddScoped<IAlertService,           MockAlertService>();
builder.Services.AddScoped<IMarketDataService,      MockMarketDataService>();
builder.Services.AddScoped<IPnLAttributionService,  MockPnLAttributionService>();
builder.Services.AddScoped<IAdminService,           MockAdminService>();
builder.Services.AddScoped<IAuditService,           MockAuditService>();
builder.Services.AddScoped<IAuthService,            JwtService>();
builder.Services.AddScoped<IOptionsService,         MockOptionsService>();
builder.Services.AddScoped<IPredictionService,      MockPredictionService>();

builder.Services.AddHostedService<HubBroadcastService>();

var app = builder.Build();

app.MapOpenApi();
app.MapScalarApiReference();

app.UseCors("AllowAll");
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.MapHub<TradingHub>("/hubs/trading");

app.MapGet("/", () => Results.Redirect("/swagger"));
app.MapGet("/health", () => Results.Ok(new { status = "healthy", timestamp = DateTime.UtcNow }));

app.Run();

public partial class Program { }
