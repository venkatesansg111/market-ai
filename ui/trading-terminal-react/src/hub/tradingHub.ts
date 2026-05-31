import * as signalR from '@microsoft/signalr';
import { API_BASE } from '../api/client';

let connection: signalR.HubConnection | null = null;

export function createHubConnection(): signalR.HubConnection {
  const token = localStorage.getItem('token');
  connection = new signalR.HubConnectionBuilder()
    .withUrl(`${API_BASE}/hubs/trading`, {
      accessTokenFactory: () => token ?? '',
    })
    .withAutomaticReconnect()
    .configureLogging(signalR.LogLevel.Warning)
    .build();
  return connection;
}

export function getHubConnection(): signalR.HubConnection | null {
  return connection;
}

export async function startHubConnection(hub: signalR.HubConnection): Promise<void> {
  if (hub.state === signalR.HubConnectionState.Disconnected) {
    await hub.start();
  }
}

export async function stopHubConnection(hub: signalR.HubConnection): Promise<void> {
  await hub.stop();
}
