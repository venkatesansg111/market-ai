import { useState, useMemo } from 'react';
import { Box, Tab, Tabs, TextField, Typography, CircularProgress } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import { marketApi } from '../api/endpoints';

const columns: ColDef<any>[] = [
  { field: 'symbol', headerName: 'Symbol', flex: 1 },
  { field: 'price', headerName: 'Price', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  {
    field: 'changePercent', headerName: 'Change %', flex: 1,
    cellStyle: (p: { value: number }) => ({ color: p.value >= 0 ? '#4caf50' : '#f44336' }),
    valueFormatter: (p: { value: number }) => `${p.value?.toFixed(2)}%`,
  },
  { field: 'volume', headerName: 'Volume', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toLocaleString() },
  { field: 'high', headerName: 'High', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
  { field: 'low', headerName: 'Low', flex: 1, valueFormatter: (p: { value: number }) => p.value?.toFixed(2) },
];

export default function MarketPage() {
  const [exchange, setExchange] = useState<'NSE' | 'BSE'>('NSE');
  const [filter, setFilter] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['watchlist', exchange],
    queryFn: () => marketApi.watchlist(exchange),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!filter) return data;
    return data.filter((r: { symbol: string }) => r.symbol.toLowerCase().includes(filter.toLowerCase()));
  }, [data, filter]);

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Market Monitor</Typography>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2 }}>
        <Tabs value={exchange} onChange={(_, v) => setExchange(v)} sx={{ minHeight: 36 }}>
          <Tab label="NSE" value="NSE" sx={{ minHeight: 36, py: 0 }} />
          <Tab label="BSE" value="BSE" sx={{ minHeight: 36, py: 0 }} />
        </Tabs>
        <TextField
          size="small"
          placeholder="Search symbol…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ ml: 'auto', width: 200 }}
        />
      </Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>}
      {isError && <Typography color="error">Error loading market data</Typography>}
      {!isLoading && !isError && (
        <Box className="ag-theme-balham-dark" sx={{ height: 'calc(100vh - 220px)' }}>
          <AgGridReact
            theme="legacy"
            rowData={filtered}
            columnDefs={columns}
            defaultColDef={{ sortable: true, resizable: true, filter: true }}
          />
        </Box>
      )}
    </Box>
  );
}
