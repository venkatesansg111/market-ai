FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY Trading.slnx .
COPY Trading.Contracts/         Trading.Contracts/
COPY Trading.Domain/            Trading.Domain/
COPY Trading.Application/       Trading.Application/
COPY Trading.Infrastructure/    Trading.Infrastructure/
COPY Trading.API/               Trading.API/
COPY Trading.API.Tests/         Trading.API.Tests/
COPY Trading.Application.Tests/ Trading.Application.Tests/

RUN dotnet restore Trading.slnx
RUN dotnet publish Trading.API/Trading.API.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .
EXPOSE 5000
ENV ASPNETCORE_URLS=http://+:5000
ENTRYPOINT ["dotnet", "Trading.API.dll"]
