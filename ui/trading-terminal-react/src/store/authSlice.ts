import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
}

const ls = (key: string) =>
  typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;

const initialState: AuthState = {
  token: ls('token'),
  username: ls('username'),
  role: ls('role'),
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials(state, action: PayloadAction<{ token: string; username: string; role: string }>) {
      const { token, username, role } = action.payload;
      state.token = token;
      state.username = username;
      state.role = role;
      localStorage.setItem('token', token);
      localStorage.setItem('username', username);
      localStorage.setItem('role', role);
    },
    logout(state) {
      state.token = null;
      state.username = null;
      state.role = null;
      localStorage.removeItem('token');
      localStorage.removeItem('username');
      localStorage.removeItem('role');
    },
  },
});

export const { setCredentials, logout } = authSlice.actions;
export default authSlice.reducer;
