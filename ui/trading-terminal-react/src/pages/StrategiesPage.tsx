import { Box, Chip, CircularProgress, Grid, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { strategiesApi } from '../api/endpoints';

const COLORS = ['#4fc3f7', '#ab47bc', '#4caf50', '#ff7043', '#ffca28', '#26c6da'];

const StatusChip = ({ value }: { value: boolean }) => (
  <Chip label={value ? 'Active' : 'Inactive'} size="small"
    sx={{ bgcolor: value ? '#1b5e20' : '#424242', color: value ? '#4caf50' : '#bdbdbd', fontWeight: 600 }} />
);

const columns: ColDef<any>[] = [
  { field: 'name', headerName: 'Name', flex: 1.5 },
  { field: 'isActive', headerName: 'Status', flex: 1, cellRenderer: (p: { value: boolean }) => <StatusChip value={p.value} /> },
  { field: 'currentRegime', headerName: 'Regime', flex: 1 },
  { field: 'sharpeRatio', headerName: 'Sharpe', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'sortinoRatio', headerName: 'Sortino', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'winRate', headerName: 'Win Rate', flex: 1, valueFormatter: (p: { value: number }) => `${(p.value * 100).toFixed(1)}%` },
  { field: 'maxDrawdown', headerName: 'Drawdown', flex: 1, valueFormatter: (p: { value: number }) => `${(p.value * 100).toFixed(1)}%` },
  { field: 'profitFactor', headerName: 'Profit Factor', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
];

export default function StrategiesPage() {
  const { data, isLoading, isError } = useQuery({ queryKey: ['strategies'], queryFn: strategiesApi.getAll });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (isError) return <Typography color="error">Error loading strategies</Typography>;

  const strategies = data ?? [];
  const pieData = strategies.map((s: { name: string; allocation?: number }, i: number) => ({
    name: s.name,
    value: s.allocation ?? Math.round(100 / (strategies.length || 1)),
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Strategy Command Center</Typography>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Box className="ag-theme-balham-dark" sx={{ height: 420 }}>
            <AgGridReact
              theme="legacy"
              rowData={strategies}
              columnDefs={columns}
              defaultColDef={{ sortable: true, resizable: true }}
            />
          </Box>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Strategy Allocation</Typography>
          <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 1, height: 380 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label>
                  {pieData.map((entry: { fill: string }, index: number) => (
                    <Cell key={index} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}
