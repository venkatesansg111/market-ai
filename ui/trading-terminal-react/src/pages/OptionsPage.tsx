import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Chip, CircularProgress, FormControl, MenuItem, Paper,
  Select, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Typography, useTheme,
} from '@mui/material';
import { optionsApi } from '../api/endpoints';

interface OptionLeg {
  oi: number; oiChange: number; volume: number;
  iv: number; ltp: number; netChange: number;
  bidQty: number; bid: number; ask: number; askQty: number;
  delta: number; gamma: number; theta: number; vega: number;
}
interface ChainRow {
  strike: number; isAtm: boolean; isCeItm: boolean; isPeItm: boolean;
  ce: OptionLeg; pe: OptionLeg;
}
interface ChainData {
  symbol: string; spotPrice: number; expiry: string; atmStrike: number;
  rows: ChainRow[];
}
interface Expiry { expiry: string; label: string; expiryType: string; }

const fmt = (n: number, dec = 2) =>
  n >= 1_00_000 ? (n / 1_00_000).toFixed(1) + 'L' :
  n >= 1_000    ? (n / 1_000).toFixed(1) + 'K'   : String(n.toFixed(dec));

const CE_COLS = ['OI', 'Chg OI', 'Volume', 'IV', 'LTP', 'Δ Chg', 'Delta'];
const PE_COLS = ['Delta', 'Δ Chg', 'LTP', 'IV', 'Volume', 'Chg OI', 'OI'];

export default function OptionsPage() {
  const theme = useTheme();
  const atmRef = useRef<HTMLTableRowElement>(null);

  const [symbol, setSymbol]   = useState('NIFTY');
  const [expiry,  setExpiry]  = useState('');

  const { data: symbols = [] } = useQuery<string[]>({
    queryKey: ['optionSymbols'],
    queryFn:  () => optionsApi.symbols(),
    staleTime: 60_000,
  });

  const { data: expiries = [] } = useQuery<Expiry[]>({
    queryKey: ['optionExpiries', symbol],
    queryFn:  () => optionsApi.expiries(symbol),
    staleTime: 60_000,
    onSuccess: (data: Expiry[]) => { if (data.length && !expiry) setExpiry(data[0].expiry); },
  } as any);

  useEffect(() => {
    if (expiries.length && !expiry) setExpiry((expiries as Expiry[])[0].expiry);
  }, [expiries]);

  const { data: chain, isLoading } = useQuery<ChainData>({
    queryKey: ['optionsChain', symbol, expiry],
    queryFn:  () => optionsApi.chain(symbol, expiry),
    enabled:  !!expiry,
    refetchInterval: 5_000,
  });

  useEffect(() => {
    if (chain && atmRef.current)
      atmRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [chain?.expiry, chain?.symbol]);

  const itmCeBg  = 'rgba(38, 166, 154, 0.10)';
  const itmPeBg  = 'rgba(239, 83, 80, 0.10)';
  const atmBg    = 'rgba(255,255,255,0.07)';
  const headerBg = theme.palette.background.paper;

  const ceCell = (leg: OptionLeg, col: string) => {
    switch (col) {
      case 'OI':      return fmt(leg.oi, 0);
      case 'Chg OI':  return <span style={{ color: leg.oiChange >= 0 ? '#26a69a' : '#ef5350' }}>{fmt(leg.oiChange, 0)}</span>;
      case 'Volume':  return fmt(leg.volume, 0);
      case 'IV':      return `${leg.iv.toFixed(2)}%`;
      case 'LTP':     return <strong>{leg.ltp.toFixed(2)}</strong>;
      case 'Δ Chg':   return <span style={{ color: leg.netChange >= 0 ? '#26a69a' : '#ef5350' }}>{leg.netChange >= 0 ? '+' : ''}{leg.netChange.toFixed(2)}</span>;
      case 'Delta':   return <span style={{ color: '#90caf9' }}>{leg.delta.toFixed(3)}</span>;
    }
  };
  const peCell = (leg: OptionLeg, col: string) => {
    switch (col) {
      case 'Delta':   return <span style={{ color: '#f48fb1' }}>{leg.delta.toFixed(3)}</span>;
      case 'Δ Chg':   return <span style={{ color: leg.netChange >= 0 ? '#26a69a' : '#ef5350' }}>{leg.netChange >= 0 ? '+' : ''}{leg.netChange.toFixed(2)}</span>;
      case 'LTP':     return <strong>{leg.ltp.toFixed(2)}</strong>;
      case 'IV':      return `${leg.iv.toFixed(2)}%`;
      case 'Volume':  return fmt(leg.volume, 0);
      case 'Chg OI':  return <span style={{ color: leg.oiChange >= 0 ? '#26a69a' : '#ef5350' }}>{fmt(leg.oiChange, 0)}</span>;
      case 'OI':      return fmt(leg.oi, 0);
    }
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {/* Header bar */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>Options Chain</Typography>

        <FormControl size="small" sx={{ minWidth: 150 }}>
          <Select value={symbol} onChange={(e) => { setSymbol(e.target.value); setExpiry(''); }}>
            {symbols.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </Select>
        </FormControl>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {(expiries as Expiry[]).map((e) => (
            <Chip
              key={e.expiry}
              label={e.label}
              size="small"
              variant={expiry === e.expiry ? 'filled' : 'outlined'}
              color={expiry === e.expiry ? 'primary' : 'default'}
              onClick={() => setExpiry(e.expiry)}
              sx={{ fontSize: 11 }}
            />
          ))}
        </Box>

        {chain && (
          <Box sx={{ ml: 'auto', display: 'flex', gap: 2, alignItems: 'center' }}>
            <Typography variant="body2" color="text.secondary">Spot</Typography>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#00d4ff' }}>
              {chain.spotPrice.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </Typography>
            <Typography variant="body2" color="text.secondary">ATM</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#fff' }}>
              {chain.atmStrike.toLocaleString('en-IN')}
            </Typography>
          </Box>
        )}
      </Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>}

      {chain && (
        <TableContainer component={Paper} sx={{ flex: 1, overflow: 'auto', bgcolor: 'background.default' }}>
          <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', minWidth: 900 }}>
            <TableHead>
              {/* Super-header: CALLS | Strike | PUTS */}
              <TableRow sx={{ bgcolor: headerBg }}>
                <TableCell colSpan={7} align="center"
                  sx={{ bgcolor: 'rgba(38,166,154,0.15)', color: '#26a69a', fontWeight: 700, fontSize: 12, py: 0.5 }}>
                  CALLS (CE)
                </TableCell>
                <TableCell align="center"
                  sx={{ bgcolor: 'rgba(255,255,255,0.05)', fontWeight: 700, fontSize: 12, py: 0.5 }}>
                  STRIKE
                </TableCell>
                <TableCell colSpan={7} align="center"
                  sx={{ bgcolor: 'rgba(239,83,80,0.15)', color: '#ef5350', fontWeight: 700, fontSize: 12, py: 0.5 }}>
                  PUTS (PE)
                </TableCell>
              </TableRow>
              {/* Column labels */}
              <TableRow sx={{ bgcolor: headerBg }}>
                {CE_COLS.map((c) => (
                  <TableCell key={`ce-${c}`} align="right"
                    sx={{ fontSize: 10, color: 'text.secondary', py: 0.5, px: 1 }}>{c}</TableCell>
                ))}
                <TableCell align="center" sx={{ fontSize: 10, color: 'text.secondary', py: 0.5, px: 0.5 }}>Price</TableCell>
                {PE_COLS.map((c) => (
                  <TableCell key={`pe-${c}`} align="right"
                    sx={{ fontSize: 10, color: 'text.secondary', py: 0.5, px: 1 }}>{c}</TableCell>
                ))}
              </TableRow>
            </TableHead>

            <TableBody>
              {chain.rows.map((row) => {
                const bg = row.isAtm ? atmBg : row.isCeItm ? itmCeBg : 'transparent';
                return (
                  <TableRow
                    key={row.strike}
                    ref={row.isAtm ? atmRef : undefined}
                    sx={{
                      bgcolor: bg,
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                      borderTop: row.isAtm ? '1px solid rgba(255,255,255,0.2)' : undefined,
                      borderBottom: row.isAtm ? '1px solid rgba(255,255,255,0.2)' : undefined,
                    }}
                  >
                    {/* CE cells */}
                    {CE_COLS.map((col) => (
                      <TableCell key={col} align="right"
                        sx={{
                          fontSize: 11, py: 0.4, px: 1,
                          bgcolor: row.isCeItm ? itmCeBg : 'transparent',
                          fontWeight: row.isAtm ? 700 : 400,
                        }}>
                        {ceCell(row.ce, col)}
                      </TableCell>
                    ))}

                    {/* Strike center */}
                    <TableCell align="center"
                      sx={{
                        fontSize: row.isAtm ? 13 : 11,
                        fontWeight: row.isAtm ? 800 : 500,
                        color: row.isAtm ? '#fff' : 'text.secondary',
                        py: 0.4, px: 0.5,
                        bgcolor: row.isAtm ? 'rgba(255,255,255,0.1)' : 'transparent',
                      }}>
                      {row.strike.toLocaleString('en-IN')}
                      {row.isAtm && <Typography component="span" sx={{ ml: 0.5, fontSize: 9, color: '#00d4ff' }}>ATM</Typography>}
                    </TableCell>

                    {/* PE cells */}
                    {PE_COLS.map((col) => (
                      <TableCell key={col} align="right"
                        sx={{
                          fontSize: 11, py: 0.4, px: 1,
                          bgcolor: row.isPeItm ? itmPeBg : 'transparent',
                          fontWeight: row.isAtm ? 700 : 400,
                        }}>
                        {peCell(row.pe, col)}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
