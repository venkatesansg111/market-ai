import { Box, CircularProgress, Grid, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import StatCard from '../components/StatCard';
import { portfolioApi, positionsApi, strategiesApi, riskApi } from '../api/endpoints';

const equityCurve = Array.from({ length: 20 }, (_, i) => ({
  day: `D${i + 1}`,
  equity: 1_000_000 + Math.round(Math.sin(i / 3) * 50_000 + i * 8_000),
}));

const positionCols: ColDef<any>[] = [
  { field: 'symbol', headerName: 'Symbol', flex: 1 },
  { field: 'quantity', headerName: 'Qty', flex: 1 },
  { field: 'averagePrice', headerName: 'Avg Price', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'unrealizedPnl', headerName: 'Unreal. PnL', flex: 1,
    cellStyle: (p: { value: number }) => ({ color: p.value >= 0 ? '#4caf50' : '#f44336' }),
    valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
];

export default function DashboardPage() {
  const portfolio = useQuery({ queryKey: ['portfolio'], queryFn: portfolioApi.get });
  const positions = useQuery({ queryKey: ['positions'], queryFn: positionsApi.getAll });
  const strategies = useQuery({ queryKey: ['strategies'], queryFn: strategiesApi.getAll });
  const risk = useQuery({ queryKey: ['risk'], queryFn: riskApi.get });

  if (portfolio.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (portfolio.isError) return <Typography color="error">Error loading portfolio data</Typography>;

  const p = portfolio.data ?? {};
  const r = risk.data ?? {};
  const activeCount = (strategies.data ?? []).filter((s: { isActive: boolean }) => s.isActive).length;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Executive Dashboard</Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Total Equity" value={`₹${(p.totalEquity ?? 0).toLocaleString()}`} color="#4fc3f7" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Daily PnL" value={`₹${(p.dailyPnl ?? 0).toLocaleString()}`} color={(p.dailyPnl ?? 0) >= 0 ? '#4caf50' : '#f44336'} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Cash" value={`₹${(p.cash ?? 0).toLocaleString()}`} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Open Positions" value={(positions.data ?? []).length} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Drawdown" value={`${(r.drawdownPct ?? 0).toFixed(2)}%`} color="#ff7043" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <StatCard title="Active Strategies" value={activeCount} color="#ab47bc" />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Equity Curve</Typography>
          <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 1, height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityCurve}>
                <defs>
                  <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4fc3f7" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#4fc3f7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => `₹${Number(v).toLocaleString()}`} />
                <Area type="monotone" dataKey="equity" stroke="#4fc3f7" fill="url(#eq)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Box>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Open Positions</Typography>
          <Box className="ag-theme-balham-dark" sx={{ height: 200 }}>
            <AgGridReact
              theme="legacy"
              rowData={positions.data ?? []}
              columnDefs={positionCols}
              defaultColDef={{ sortable: true, resizable: true }}
            />
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}
