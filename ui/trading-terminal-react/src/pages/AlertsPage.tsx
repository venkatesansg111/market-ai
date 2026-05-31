import { useState } from 'react';
import { Box, Button, Chip, CircularProgress, Tab, Tabs, Typography } from '@mui/material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi } from '../api/endpoints';

const TABS = ['All', 'WARNING', 'CRITICAL', 'INFO'];

const sevColor: Record<string, { bg: string; fg: string }> = {
  CRITICAL: { bg: '#b71c1c', fg: '#ef9a9a' },
  WARNING:  { bg: '#e65100', fg: '#ffcc80' },
  INFO:     { bg: '#0d47a1', fg: '#90caf9' },
};

interface Alert {
  alertId: string;
  title: string;
  message: string;
  severity: string;
  timestamp: string;
  acknowledged: boolean;
}

export default function AlertsPage() {
  const [tab, setTab] = useState(0);
  const queryClient = useQueryClient();

  const severity = tab === 0 ? undefined : TABS[tab];
  const { data, isLoading, isError } = useQuery<Alert[]>({
    queryKey: ['alerts', severity],
    queryFn: () => alertsApi.getAll(severity),
  });

  const ackMut = useMutation({
    mutationFn: (id: string) => alertsApi.acknowledge(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (isError) return <Typography color="error">Error loading alerts</Typography>;

  const alerts = data ?? [];

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Alert Center</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        {TABS.map((t) => <Tab key={t} label={t} />)}
      </Tabs>

      {alerts.length === 0 && <Typography color="text.secondary">No alerts found.</Typography>}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {alerts.map((a) => {
          const c = sevColor[a.severity] ?? { bg: '#424242', fg: '#bdbdbd' };
          return (
            <Box key={a.alertId} sx={{
              display: 'flex', alignItems: 'flex-start', gap: 2, p: 2,
              bgcolor: 'background.paper', borderRadius: 1,
              borderLeft: `4px solid ${c.fg}`,
              opacity: a.acknowledged ? 0.5 : 1,
            }}>
              <Chip label={a.severity} size="small"
                sx={{ bgcolor: c.bg, color: c.fg, fontWeight: 700, minWidth: 80 }} />
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{a.title}</Typography>
                <Typography variant="caption" color="text.secondary">{a.message}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {a.timestamp ? new Date(a.timestamp).toLocaleString() : ''}
                </Typography>
              </Box>
              {!a.acknowledged && (
                <Button size="small" variant="outlined"
                  disabled={ackMut.isPending}
                  onClick={() => ackMut.mutate(a.alertId)}>
                  Acknowledge
                </Button>
              )}
              {a.acknowledged && <Chip label="ACK" size="small" color="default" />}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
