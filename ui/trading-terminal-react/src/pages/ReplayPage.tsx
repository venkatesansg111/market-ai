import { useState } from 'react';
import { Box, Button, Card, CardContent, Chip, CircularProgress, FormControl,
  InputLabel, LinearProgress, MenuItem, Select, Typography } from '@mui/material';
import { Pause, PlayArrow, Stop } from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { replayApi } from '../api/endpoints';

const SPEEDS = [1, 5, 10, 20];

interface ReplayStatus {
  status: string;
  speed: number;
  processedEvents: number;
  totalEvents: number;
  currentTimestamp?: string;
  message?: string;
}

export default function ReplayPage() {
  const [speed, setSpeed] = useState(1);
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery<ReplayStatus>({
    queryKey: ['replayStatus'],
    queryFn: replayApi.status,
    refetchInterval: 2000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['replayStatus'] });

  const startMut = useMutation({ mutationFn: () => replayApi.start(speed), onSuccess: invalidate });
  const pauseMut = useMutation({ mutationFn: replayApi.pause, onSuccess: invalidate });
  const stopMut = useMutation({ mutationFn: replayApi.stop, onSuccess: invalidate });

  const statusColor: Record<string, string> = { RUNNING: '#4caf50', PAUSED: '#ff9800', STOPPED: '#f44336', IDLE: '#757575' };
  const s = data ?? ({} as ReplayStatus);
  const progress = s.totalEvents ? Math.round((s.processedEvents / s.totalEvents) * 100) : 0;
  const isRunning = s.status === 'RUNNING';
  const isPaused = s.status === 'PAUSED';

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (isError) return <Typography color="error">Error loading replay status</Typography>;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Replay Center</Typography>
      <Card sx={{ maxWidth: 640 }}>
        <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="subtitle2">Status</Typography>
            <Chip label={s.status ?? 'IDLE'} size="small"
              sx={{ bgcolor: `${statusColor[s.status] ?? '#757575'}22`, color: statusColor[s.status] ?? '#bdbdbd', fontWeight: 700 }} />
            {s.currentTimestamp && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                {new Date(s.currentTimestamp).toLocaleString()}
              </Typography>
            )}
          </Box>

          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
              <Typography variant="caption" color="text.secondary">Progress</Typography>
              <Typography variant="caption" color="text.secondary">
                {s.processedEvents?.toLocaleString() ?? 0} / {s.totalEvents?.toLocaleString() ?? 0} events ({progress}%)
              </Typography>
            </Box>
            <LinearProgress variant="determinate" value={progress} sx={{ height: 8, borderRadius: 4 }} />
          </Box>

          {s.message && <Typography variant="body2" color="text.secondary">{s.message}</Typography>}

          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Speed</InputLabel>
              <Select value={speed} label="Speed" onChange={(e) => setSpeed(Number(e.target.value))} disabled={isRunning}>
                {SPEEDS.map((x) => <MenuItem key={x} value={x}>{x}x</MenuItem>)}
              </Select>
            </FormControl>
            <Button variant="contained" color="success" startIcon={<PlayArrow />}
              disabled={isRunning || startMut.isPending}
              onClick={() => startMut.mutate()}>
              {isPaused ? 'Resume' : 'Play'}
            </Button>
            <Button variant="outlined" color="warning" startIcon={<Pause />}
              disabled={!isRunning || pauseMut.isPending}
              onClick={() => pauseMut.mutate()}>
              Pause
            </Button>
            <Button variant="outlined" color="error" startIcon={<Stop />}
              disabled={(!isRunning && !isPaused) || stopMut.isPending}
              onClick={() => stopMut.mutate()}>
              Stop
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
