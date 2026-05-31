import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Chip, CircularProgress, Divider, InputAdornment,
  List, ListItemButton, Paper, TextField, Typography,
} from '@mui/material';
import { Search, TrendingDown, TrendingUp } from '@mui/icons-material';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { UTCTimestamp } from 'lightweight-charts';
import { marketApi } from '../api/endpoints';

interface WatchItem {
  symbol: string; price: number; changePercent: number;
  volume: number; high: number; low: number;
}
interface Candle {
  symbol: string; timeframe: string;
  open: number; high: number; low: number; close: number;
  volume: number; timestamp: string;
}

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '1D'];
const CANDLE_LIMITS: Record<string, number> = { '1m': 120, '5m': 100, '15m': 80, '1h': 60, '1D': 90 };

export default function MarketPage() {
  const [exchange, setExchange]   = useState<'NSE' | 'BSE'>('NSE');
  const [filter, setFilter]       = useState('');
  const [selected, setSelected]   = useState('RELIANCE');
  const [timeframe, setTimeframe] = useState('5m');

  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null);
  const candleRef    = useRef<any>(null);
  const volumeRef    = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: watchlist = [] } = useQuery<WatchItem[]>({
    queryKey: ['watchlist', exchange],
    queryFn:  () => marketApi.watchlist(exchange),
    refetchInterval: 5_000,
  });

  const { data: candles = [], isLoading: loadingCandles } = useQuery<Candle[]>({
    queryKey: ['candles', selected, timeframe],
    queryFn:  () => marketApi.candles(selected, timeframe, CANDLE_LIMITS[timeframe] ?? 100),
    enabled:  !!selected,
    refetchInterval: 5_000,
  });

  // Create chart once on mount
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      layout: { background: { color: '#0a0e1a' }, textColor: '#c8cdd6' },
      grid:   { vertLines: { color: '#1a2236' }, horzLines: { color: '#1a2236' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#1a2236' },
      timeScale: { borderColor: '#1a2236', timeVisible: true, secondsVisible: false },
    });
    const candle = (chart as any).addSeries(CandlestickSeries, {
      upColor: '#26a69a', downColor: '#ef5350',
      borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    });
    const volume = (chart as any).addSeries(HistogramSeries, {
      color: '#26a69a26', priceFormat: { type: 'volume' }, priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

    chartRef.current  = chart;
    candleRef.current = candle;
    volumeRef.current = volume;

    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    });
    ro.observe(containerRef.current);
    return () => { ro.disconnect(); chart.remove(); };
  }, []);

  // Push data whenever candles change
  useEffect(() => {
    if (!candleRef.current || !candles.length) return;
    const cd = candles
      .filter((c) => c.open != null)
      .map((c) => ({
        time:  Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        open:  Number(c.open), high: Number(c.high),
        low:   Number(c.low),  close: Number(c.close),
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    const vd = candles
      .filter((c) => c.volume != null)
      .map((c) => ({
        time:  Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        value: Number(c.volume),
        color: Number(c.close) >= Number(c.open) ? '#26a69a40' : '#ef535040',
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    candleRef.current.setData(cd);
    volumeRef.current.setData(vd);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  const filtered = watchlist.filter((w) =>
    w.symbol.toLowerCase().includes(filter.toLowerCase())
  );
  const selectedItem = watchlist.find((w) => w.symbol === selected);
  const isUp = (selectedItem?.changePercent ?? 0) >= 0;

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 80px)', gap: 1.5 }}>
      {/* LEFT: Watchlist */}
      <Paper sx={{ width: 240, display: 'flex', flexDirection: 'column', overflow: 'hidden', flexShrink: 0 }}>
        {/* Exchange tabs */}
        <Box sx={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {(['NSE', 'BSE'] as const).map((ex) => (
            <Box key={ex} onClick={() => setExchange(ex)}
              sx={{
                flex: 1, py: 1, textAlign: 'center', cursor: 'pointer',
                fontSize: 13, fontWeight: 600,
                color: exchange === ex ? 'primary.main' : 'text.secondary',
                borderBottom: exchange === ex ? '2px solid' : '2px solid transparent',
                borderColor: exchange === ex ? 'primary.main' : 'transparent',
              }}>
              {ex}
            </Box>
          ))}
        </Box>

        {/* Search */}
        <Box sx={{ p: 1 }}>
          <TextField size="small" fullWidth placeholder="Search…" value={filter}
            onChange={(e) => setFilter(e.target.value)}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search sx={{ fontSize: 16 }} /></InputAdornment> } }}
            sx={{ '& .MuiInputBase-input': { fontSize: 12 } }}
          />
        </Box>
        <Divider />

        {/* Symbol list */}
        <List dense sx={{ overflow: 'auto', flex: 1, p: 0 }}>
          {filtered.map((item) => {
            const up = item.changePercent >= 0;
            return (
              <ListItemButton key={item.symbol} selected={item.symbol === selected}
                onClick={() => setSelected(item.symbol)}
                sx={{
                  px: 1.5, py: 0.8,
                  '&.Mui-selected': { bgcolor: 'rgba(0,212,255,0.08)', borderRight: '2px solid #00d4ff' },
                }}>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontSize: 12, fontWeight: 600 }}>{item.symbol}</Typography>
                  <Typography sx={{ fontSize: 10, color: 'text.secondary' }}>
                    Vol: {(item.volume / 1_00_000).toFixed(1)}L
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography sx={{ fontSize: 12, fontWeight: 600 }}>
                    {item.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </Typography>
                  <Box sx={{ fontSize: 10, color: up ? '#26a69a' : '#ef5350', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 0.3 }}>
                    {up ? <TrendingUp sx={{ fontSize: 10 }} /> : <TrendingDown sx={{ fontSize: 10 }} />}
                    {up ? '+' : ''}{item.changePercent.toFixed(2)}%
                  </Box>
                </Box>
              </ListItemButton>
            );
          })}
        </List>
      </Paper>

      {/* RIGHT: Chart panel */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        {/* Chart header */}
        <Paper sx={{ px: 2, py: 1, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Typography sx={{ fontWeight: 700, fontSize: 15 }}>{selected}</Typography>
          {selectedItem && (
            <>
              <Typography sx={{ fontSize: 19, fontWeight: 800 }}>
                {selectedItem.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </Typography>
              <Chip size="small"
                label={`${isUp ? '+' : ''}${selectedItem.changePercent.toFixed(2)}%`}
                sx={{ bgcolor: isUp ? 'rgba(38,166,154,0.2)' : 'rgba(239,83,80,0.2)', color: isUp ? '#26a69a' : '#ef5350' }}
              />
              <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
                H: {selectedItem.high.toFixed(2)} &nbsp;|&nbsp; L: {selectedItem.low.toFixed(2)}
              </Typography>
            </>
          )}
          <Box sx={{ ml: 'auto', display: 'flex', gap: 0.5 }}>
            {TIMEFRAMES.map((tf) => (
              <Chip key={tf} label={tf} size="small"
                variant={timeframe === tf ? 'filled' : 'outlined'}
                color={timeframe === tf ? 'primary' : 'default'}
                onClick={() => setTimeframe(tf)}
                sx={{ fontSize: 11, cursor: 'pointer' }}
              />
            ))}
          </Box>
        </Paper>

        {/* Candlestick chart */}
        <Paper sx={{ flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0 }}>
          {loadingCandles && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2, bgcolor: 'rgba(0,0,0,0.4)' }}>
              <CircularProgress size={32} />
            </Box>
          )}
          <Box ref={containerRef} sx={{ width: '100%', height: '100%' }} />
        </Paper>
      </Box>
    </Box>
  );
}
