import api from './client';

export const authApi = {
  login: (username: string, password: string) =>
    api.post('/api/auth/login', { username, password }).then((r) => r.data),
  me: () => api.get('/api/auth/me').then((r) => r.data),
};

export const portfolioApi = {
  get: () => api.get('/api/portfolio').then((r) => r.data),
  history: (days = 30) => api.get(`/api/portfolio/history?days=${days}`).then((r) => r.data),
  exposure: () => api.get('/api/portfolio/exposure').then((r) => r.data),
};

export const positionsApi = {
  getAll: () => api.get('/api/positions').then((r) => r.data),
  getBySymbol: (symbol: string) => api.get(`/api/positions/${symbol}`).then((r) => r.data),
};

export const ordersApi = {
  getAll: (status?: string, symbol?: string) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (symbol) params.set('symbol', symbol);
    return api.get(`/api/orders?${params}`).then((r) => r.data);
  },
  getById: (id: string) => api.get(`/api/orders/${id}`).then((r) => r.data),
  cancel: (id: string) => api.post(`/api/orders/${id}/cancel`).then((r) => r.data),
};

export const tradesApi = {
  getAll: (symbol?: string, strategy?: string) => {
    const params = new URLSearchParams();
    if (symbol) params.set('symbol', symbol);
    if (strategy) params.set('strategy', strategy);
    return api.get(`/api/trades?${params}`).then((r) => r.data);
  },
  getById: (id: string) => api.get(`/api/trades/${id}`).then((r) => r.data),
};

export const strategiesApi = {
  getAll: () => api.get('/api/strategies').then((r) => r.data),
  performance: () => api.get('/api/strategies/performance').then((r) => r.data),
  regimes: () => api.get('/api/strategies/regimes').then((r) => r.data),
};

export const riskApi = {
  get: () => api.get('/api/risk').then((r) => r.data),
  exposure: () => api.get('/api/risk/exposure').then((r) => r.data),
  alerts: () => api.get('/api/risk/alerts').then((r) => r.data),
};

export const explainApi = {
  trade: (tradeId: string) => api.get(`/api/explain/trade/${tradeId}`).then((r) => r.data),
  all: () => api.get('/api/explain/trades').then((r) => r.data),
};

export const replayApi = {
  status: () => api.get('/api/replay/status').then((r) => r.data),
  start: (speed = 1.0) => api.post(`/api/replay/start?speed=${speed}`).then((r) => r.data),
  pause: () => api.post('/api/replay/pause').then((r) => r.data),
  stop: () => api.post('/api/replay/stop').then((r) => r.data),
};

export const healthApi = {
  get: () => api.get('/api/system-health').then((r) => r.data),
};

export const alertsApi = {
  getAll: (severity?: string, category?: string) => {
    const params = new URLSearchParams();
    if (severity) params.set('severity', severity);
    if (category) params.set('category', category);
    return api.get(`/api/alerts?${params}`).then((r) => r.data);
  },
  acknowledge: (alertId: string) => api.post(`/api/alerts/${alertId}/acknowledge`).then((r) => r.data),
};

export const marketApi = {
  watchlist: (exchange = 'NSE') => api.get(`/api/market/watchlist?exchange=${exchange}`).then((r) => r.data),
  candles: (symbol: string, timeframe = '1m', limit = 100) =>
    api.get(`/api/market/candles/${symbol}?timeframe=${timeframe}&limit=${limit}`).then((r) => r.data),
  tick: (symbol: string) => api.get(`/api/market/tick/${symbol}`).then((r) => r.data),
};

export const pnlApi = {
  attribution: () => api.get('/api/pnl/attribution').then((r) => r.data),
};

export const adminApi = {
  enableStrategy: (name: string) => api.post('/api/admin/strategy/enable', { action: 'enable', target: name }).then((r) => r.data),
  disableStrategy: (name: string) => api.post('/api/admin/strategy/disable', { action: 'disable', target: name }).then((r) => r.data),
  pauseTrading: () => api.post('/api/admin/trading/pause').then((r) => r.data),
  resumeTrading: () => api.post('/api/admin/trading/resume').then((r) => r.data),
  killSwitch: () => api.post('/api/admin/kill-switch').then((r) => r.data),
  audit: (limit = 100) => api.get(`/api/admin/audit?limit=${limit}`).then((r) => r.data),
  getRiskLimits: () => api.get('/api/admin/risk-limits').then((r) => r.data),
  updateRiskLimit: (target: string, value: string) =>
    api.post('/api/admin/risk-limits', { action: 'update', target, value }).then((r) => r.data),
};
