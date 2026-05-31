import { Box, Chip, CircularProgress, Grid, Paper, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import { TrendingUp, TrendingDown } from '@mui/icons-material';
import StatCard from '../components/StatCard';
import { portfolioApi, positionsApi, strategiesApi, riskApi, predictionsApi } from '../api/endpoints';

const positionCols: ColDef<any>[] = [
  { field: 'symbol',       headerName: 'Symbol',    flex: 1 },
  { field: 'quantity',     headerName: 'Qty',       flex: 1 },
  { field: 'avgPrice',     headerName: 'Avg',       flex: 1, valueFormatter: (p: any) => p.value?.toFixed(2) },
  { field: 'currentPrice', headerName: 'LTP',       flex: 1, valueFormatter: (p: any) => p.value?.toFixed(2) },
  {
    field: 'unrealizedPnl', headerName: 'PnL', flex: 1,
    cellStyle: (p: any) => ({ color: p.value >= 0 ? '#26a69a' : '#ef5350' }),
    valueFormatter: (p: any) => p.value != null ? `₹${p.value.toFixed(0)}` : '',
  },
  { field: 'side', headerName: 'Side', width: 70 },
];

interface Prediction {
  symbol: string; signal: string; optionType: string;
  strike: number; expiry: string; confidence: number;
  regime: string; targetPrice: number; stopLoss: number;
  timeframe: string; expectedReturn: number; riskReward: number; reason: string;
}

export default function DashboardPage() {
  const portfolio   = useQuery({ queryKey: ['portfolio'],   queryFn: portfolioApi.get });
  const history     = useQuery({ queryKey: ['portHistory'], queryFn: () => portfolioApi.history(30), staleTime: 60_000 } as any);
  const positions   = useQuery({ queryKey: ['positions'],   queryFn: positionsApi.getAll });
  const strategies  = useQuery({ queryKey: ['strategies'],  queryFn: strategiesApi.getAll });
  const risk        = useQuery({ queryKey: ['risk'],        queryFn: riskApi.get });
  const predictions = useQuery({ queryKey: ['predictions'], queryFn: predictionsApi.getAll, refetchInterval: 30_000 });

  if (portfolio.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;

  const p = portfolio.data ?? {};
  const r = risk.data ?? {};
  const activeCount = (strategies.data ?? []).filter((s: any) => s.status === 'active').length;
  const preds: Prediction[] = predictions.data ?? [];

  // Build equity curve from real API data
  const histData = (history.data as any)?.equityCurve ?? [];
  const equityCurve = histData.map((pt: any) => ({
    day:    new Date(pt.timestamp).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
    equity: Math.round(pt.value),
  }));

  const equity   = p.equity   ?? 0;
  const dailyPnl = p.dailyPnl ?? 0;
  const cash     = p.cash     ?? 0;
  const drawdown = r.drawdownPct ?? 0;

  return (
    <Box sx={{ pb: 2 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Dashboard</Typography>

      {/* ── Stats row ── */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        {[
          { title: 'Portfolio Value', value: `₹${(equity/100000).toFixed(2)}L`,  color: '#00d4ff' },
          { title: 'Daily P&L',       value: `₹${(dailyPnl).toLocaleString('en-IN')}`, color: dailyPnl >= 0 ? '#26a69a' : '#ef5350', subtitle: dailyPnl >= 0 ? '▲ Profit' : '▼ Loss' },
          { title: 'Cash',            value: `₹${(cash/100000).toFixed(1)}L`,    color: '#ab47bc' },
          { title: 'Open Positions',  value: (positions.data ?? []).length,      color: '#ffa726' },
          { title: 'Drawdown',        value: `${drawdown.toFixed(2)}%`,           color: drawdown > 5 ? '#ef5350' : '#26a69a' },
          { title: 'Active Strategies', value: `${activeCount}/4`,               color: '#7986cb' },
        ].map((card) => (
          <Grid key={card.title} size={{ xs: 6, sm: 4, md: 2 }}>
            <StatCard title={card.title} value={card.value} subtitle={card.subtitle} color={card.color} />
          </Grid>
        ))}
      </Grid>

      {/* ── Main row: Equity curve + Predictions ── */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        {/* Equity Curve */}
        <Grid size={{ xs: 12, md: 7 }}>
          <Paper sx={{ p: 2, height: 260 }}>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>Equity Curve (30D)</Typography>
            {equityCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height="85%">
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="day" tick={{ fontSize: 9 }} interval={4} />
                  <YAxis tick={{ fontSize: 9 }} tickFormatter={(v) => `${(v / 100000).toFixed(1)}L`} width={45} />
                  <Tooltip
                    formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, 'Equity']}
                    contentStyle={{ fontSize: 11, background: '#1a2236' }}
                  />
                  <Area type="monotone" dataKey="equity" stroke="#00d4ff" fill="url(#eq)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '85%' }}>
                <CircularProgress size={24} />
              </Box>
            )}
          </Paper>
        </Grid>

        {/* AI Predictions */}
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper sx={{ p: 2, height: 260, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
              AI Trade Predictions
              <Chip label="LIVE" size="small" color="success" sx={{ ml: 1, fontSize: 9, height: 16 }} />
            </Typography>
            <Box sx={{ flex: 1, overflow: 'auto' }}>
              {preds.slice(0, 5).map((pred, i) => (
                <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.6, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <Chip
                    label={pred.signal}
                    size="small"
                    sx={{
                      bgcolor: pred.signal === 'BUY' ? 'rgba(38,166,154,0.2)' : 'rgba(239,83,80,0.2)',
                      color:   pred.signal === 'BUY' ? '#26a69a' : '#ef5350',
                      fontSize: 10, fontWeight: 700, minWidth: 40,
                    }}
                  />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: 11, fontWeight: 600 }}>
                      {pred.symbol}
                      {pred.optionType !== 'STOCK' && ` ${pred.strike} ${pred.optionType}`}
                    </Typography>
                    <Typography sx={{ fontSize: 10, color: 'text.secondary' }} noWrap>
                      {pred.regime} · {pred.timeframe}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.3, color: pred.signal === 'BUY' ? '#26a69a' : '#ef5350', fontSize: 11, fontWeight: 700 }}>
                      {pred.signal === 'BUY' ? <TrendingUp sx={{ fontSize: 12 }} /> : <TrendingDown sx={{ fontSize: 12 }} />}
                      {pred.expectedReturn.toFixed(1)}%
                    </Box>
                    <Typography sx={{ fontSize: 10, color: '#ffa726' }}>
                      {(pred.confidence * 100).toFixed(0)}% conf
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* ── Positions Grid ── */}
      <Paper sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>Open Positions</Typography>
        <Box className="ag-theme-balham-dark" sx={{ height: 200 }}>
          <AgGridReact
            theme="legacy"
            rowData={positions.data ?? []}
            columnDefs={positionCols}
            defaultColDef={{ sortable: true, resizable: true }}
          />
        </Box>
      </Paper>
    </Box>
  );
}
