import { describe, it, expect, beforeEach, vi } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';

// Mock localStorage before importing authSlice
const mockStorage: Record<string, string> = {};
vi.stubGlobal('localStorage', {
  getItem: (k: string) => mockStorage[k] ?? null,
  setItem: (k: string, v: string) => { mockStorage[k] = v; },
  removeItem: (k: string) => { delete mockStorage[k]; },
  clear: () => { Object.keys(mockStorage).forEach((k) => delete mockStorage[k]); },
});

import authReducer, { setCredentials, logout } from '../store/authSlice';

function makeStore() {
  return configureStore({ reducer: { auth: authReducer } });
}

describe('authSlice', () => {
  beforeEach(() => localStorage.clear());

  it('initial state has null token', () => {
    const store = makeStore();
    expect(store.getState().auth.token).toBeNull();
  });

  it('setCredentials stores token and role in state', () => {
    const store = makeStore();
    store.dispatch(setCredentials({ token: 'test-token', username: 'admin', role: 'Admin' }));
    const state = store.getState().auth;
    expect(state.token).toBe('test-token');
    expect(state.username).toBe('admin');
    expect(state.role).toBe('Admin');
  });

  it('setCredentials persists to localStorage', () => {
    const store = makeStore();
    store.dispatch(setCredentials({ token: 'tok123', username: 'user', role: 'Viewer' }));
    expect(localStorage.getItem('token')).toBe('tok123');
    expect(localStorage.getItem('role')).toBe('Viewer');
  });

  it('logout clears state', () => {
    const store = makeStore();
    store.dispatch(setCredentials({ token: 'tok', username: 'u', role: 'Trader' }));
    store.dispatch(logout());
    const state = store.getState().auth;
    expect(state.token).toBeNull();
    expect(state.username).toBeNull();
    expect(state.role).toBeNull();
  });

  it('logout removes from localStorage', () => {
    const store = makeStore();
    store.dispatch(setCredentials({ token: 'tok', username: 'u', role: 'Trader' }));
    store.dispatch(logout());
    expect(localStorage.getItem('token')).toBeNull();
  });
});
