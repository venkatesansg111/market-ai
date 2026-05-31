using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Trading.Domain;

namespace Trading.API.Controllers;

[ApiController]
[Route("api/predictions")]
[Authorize]
public class PredictionsController(IPredictionService predictions) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Get() =>
        Ok(await predictions.GetPredictionsAsync());
}
