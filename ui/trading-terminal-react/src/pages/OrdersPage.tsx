import { useState } from 'react';
import { Box, CircularProgress, FormControl, InputLabel, MenuItem, Select, Tab, Tabs, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import { ordersApi, tradesApi } from '../api/endpoints';

const orderCols: ColDef<any>[] = [
  { field: 'orderId', headerName: 'Order ID', flex: 1.2 },
  { field: 'symbol', headerName: 'Symbol', flex: 1 },
  { field: 'action', headerName: 'Action', flex: 0.8 },
  { field: 'quantity', headerName: 'Qty', flex: 0.8 },
  { field: 'status', headerName: 'Status', flex: 1,
    cellStyle: (p: { value: string }) => ({ color: p.value === 'FILLED' ? '#4caf50' : p.value === 'CANCELLED' ? '#f44336' : '#ffca28' }) },
  { field: 'strategyName', headerName: 'Strategy', flex: 1.2 },
  { field: 'createdAt', headerName: 'Created At', flex: 1.5, valueFormatter: (p: { value: string }) => p.value ? new Date(p.value).toLocaleString() : '' },
];

const tradeCols: ColDef<any>[] = [
  { field: 'tradeId', headerName: 'Trade ID', flex: 1.2 },
  { field: 'symbol', headerName: 'Symbol', flex: 1 },
  { field: 'strategyName', headerName: 'Strategy', flex: 1.2 },
  { field: 'entryPrice', headerName: 'Entry Price', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'exitPrice', headerName: 'Exit Price', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'realizedPnl', headerName: 'PnL', flex: 1,
    cellStyle: (p: { value: number }) => ({ color: p.value >= 0 ? '#4caf50' : '#f44336' }),
    valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'entryTime', headerName: 'Entry Time', flex: 1.5, valueFormatter: (p: { value: string }) => p.value ? new Date(p.value).toLocaleString() : '' },
];

const STATUS_OPTIONS = ['', 'PENDING', 'FILLED', 'CANCELLED', 'REJECTED'];

export default function OrdersPage() {
  const [tab, setTab] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');

  const orders = useQuery({ queryKey: ['orders', statusFilter], queryFn: () => ordersApi.getAll(statusFilter || undefined) });
  const trades = useQuery({ queryKey: ['trades'], queryFn: () => tradesApi.getAll() });

  const loading = tab === 0 ? orders.isLoading : trades.isLoading;
  const error = tab === 0 ? orders.isError : trades.isError;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>OMS Dashboard</Typography>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ minHeight: 36 }}>
          <Tab label="Orders" sx={{ minHeight: 36, py: 0 }} />
          <Tab label="Trades" sx={{ minHeight: 36, py: 0 }} />
        </Tabs>
        {tab === 0 && (
          <FormControl size="small" sx={{ ml: 'auto', minWidth: 150 }}>
            <InputLabel>Status</InputLabel>
            <Select value={statusFilter} label="Status" onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((s) => <MenuItem key={s} value={s}>{s || 'All'}</MenuItem>)}
            </Select>
          </FormControl>
        )}
      </Box>

      {loading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>}
      {error && <Typography color="error">Error loading data</Typography>}
      {!loading && !error && (
        <Box className="ag-theme-balham-dark" sx={{ height: 'calc(100vh - 220px)' }}>
          <AgGridReact
            theme="legacy"
            rowData={tab === 0 ? (orders.data ?? []) : (trades.data ?? [])}
            columnDefs={tab === 0 ? orderCols : tradeCols}
            defaultColDef={{ sortable: true, resizable: true, filter: true }}
          />
        </Box>
      )}
    </Box>
  );
}
