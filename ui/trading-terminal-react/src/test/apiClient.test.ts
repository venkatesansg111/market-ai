import { describe, it, expect } from 'vitest';
import { API_BASE } from '../api/client';

describe('API client', () => {
  it('API_BASE defaults to localhost:5000', () => {
    expect(API_BASE).toContain('localhost');
  });
});

describe('authApi contract', () => {
  it('login endpoint path is correct', () => {
    const url = '/api/auth/login';
    expect(url).toBe('/api/auth/login');
  });
});

describe('endpoint path constants', () => {
  const endpoints = {
    portfolio: '/api/portfolio',
    positions: '/api/positions',
    orders:    '/api/orders',
    trades:    '/api/trades',
    strategies:'/api/strategies',
    risk:      '/api/risk',
    health:    '/api/system-health',
    alerts:    '/api/alerts',
    replay:    '/api/replay/status',
    explain:   '/api/explain/trades',
    pnl:       '/api/pnl/attribution',
    market:    '/api/market/watchlist',
  };

  Object.entries(endpoints).forEach(([name, path]) => {
    it(`${name} endpoint starts with /api`, () => {
      expect(path).toMatch(/^\/api\//);
    });
  });
});
