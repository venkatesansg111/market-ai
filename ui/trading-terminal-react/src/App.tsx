import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { store, useAppSelector } from './store';
import { darkTheme } from './theme';
import Layout from './components/Layout';

import LoginPage      from './pages/LoginPage';
import DashboardPage  from './pages/DashboardPage';
import MarketPage     from './pages/MarketPage';
import StrategiesPage from './pages/StrategiesPage';
import RiskPage       from './pages/RiskPage';
import OrdersPage     from './pages/OrdersPage';
import ExplainPage    from './pages/ExplainPage';
import ReplayPage     from './pages/ReplayPage';
import AlertsPage     from './pages/AlertsPage';
import HealthPage     from './pages/HealthPage';
import AdminPage      from './pages/AdminPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAppSelector((s) => s.auth.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route path="/"          element={<DashboardPage />} />
                <Route path="/market"    element={<MarketPage />} />
                <Route path="/strategies"element={<StrategiesPage />} />
                <Route path="/risk"      element={<RiskPage />} />
                <Route path="/orders"    element={<OrdersPage />} />
                <Route path="/explain"   element={<ExplainPage />} />
                <Route path="/replay"    element={<ReplayPage />} />
                <Route path="/alerts"    element={<AlertsPage />} />
                <Route path="/health"    element={<HealthPage />} />
                <Route path="/admin"     element={<AdminPage />} />
                <Route path="*"          element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </PrivateRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={darkTheme}>
          <CssBaseline />
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </Provider>
  );
}
