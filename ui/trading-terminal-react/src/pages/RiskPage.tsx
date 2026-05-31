import { Box, Chip, CircularProgress, Grid, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import StatCard from '../components/StatCard';
import { riskApi } from '../api/endpoints';

const severityColor: Record<string, string> = {
  CRITICAL: '#f44336',
  WARNING: '#ff9800',
  INFO: '#2196f3',
};

export default function RiskPage() {
  const risk = useQuery({ queryKey: ['risk'], queryFn: riskApi.get });
  const exposure = useQuery({ queryKey: ['riskExposure'], queryFn: riskApi.exposure });
  const alerts = useQuery({ queryKey: ['riskAlerts'], queryFn: riskApi.alerts });

  if (risk.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (risk.isError) return <Typography color="error">Error loading risk data</Typography>;

  const r = risk.data ?? {};
  const exposureData: { symbol: string; exposure: number }[] = exposure.data ?? [];
  const alertList: { id: string; message: string; severity: string; symbol?: string }[] = alerts.data ?? [];

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Risk Command Center</Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard title="Total Exposure" value={`₹${(r.totalExposure ?? 0).toLocaleString()}`} color="#4fc3f7" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard title="Leverage" value={`${(r.leverage ?? 0).toFixed(2)}x`} color="#ff7043" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard title="Drawdown" value={`${(r.drawdownPct ?? 0).toFixed(2)}%`} color="#f44336" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard title="VaR 95%" value={`₹${(r.var95 ?? 0).toLocaleString()}`} color="#ab47bc" />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Exposure by Symbol</Typography>
          <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 1, height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={exposureData.slice(0, 15)}>
                <XAxis dataKey="symbol" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => `₹${Number(v).toLocaleString()}`} />
                <Bar dataKey="exposure" fill="#4fc3f7" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Box>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Risk Alerts</Typography>
          <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 1.5, height: 260, overflowY: 'auto' }}>
            {alertList.length === 0 && <Typography color="text.secondary" variant="body2">No active alerts</Typography>}
            {alertList.map((a) => (
              <Box key={a.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <Chip label={a.severity} size="small"
                  sx={{ bgcolor: `${severityColor[a.severity] ?? '#757575'}22`, color: severityColor[a.severity] ?? '#bdbdbd', fontWeight: 600, minWidth: 72 }} />
                <Typography variant="caption" sx={{ flex: 1 }}>{a.message}</Typography>
              </Box>
            ))}
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}
