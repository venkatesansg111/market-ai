import { useState } from 'react';
import { Box, Button, Card, CardContent, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogContentText, DialogTitle, Divider, TextField, Typography } from '@mui/material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';
import { strategiesApi, adminApi } from '../api/endpoints';
import { useAppSelector } from '../store';

interface Strategy { name: string; isActive: boolean }
interface AuditEntry { id: string; action: string; target: string; performedBy: string; timestamp: string }

const auditCols: ColDef<any>[] = [
  { field: 'timestamp', headerName: 'Time', flex: 1.5, valueFormatter: (p: { value: string }) => p.value ? new Date(p.value).toLocaleString() : '' },
  { field: 'action', headerName: 'Action', flex: 1 },
  { field: 'target', headerName: 'Target', flex: 1.5 },
  { field: 'performedBy', headerName: 'User', flex: 1 },
];

export default function AdminPage() {
  const role = useAppSelector((s) => s.auth.role);
  const [killDialog, setKillDialog] = useState(false);
  const [maxDrawdown, setMaxDrawdown] = useState('');
  const [maxLeverage, setMaxLeverage] = useState('');
  const qc = useQueryClient();

  const strategies = useQuery<Strategy[]>({ queryKey: ['strategies'], queryFn: strategiesApi.getAll });
  const audit = useQuery<AuditEntry[]>({ queryKey: ['audit'], queryFn: () => adminApi.audit() });

  const invalidateStrategies = () => qc.invalidateQueries({ queryKey: ['strategies'] });
  const enableMut = useMutation({ mutationFn: (name: string) => adminApi.enableStrategy(name), onSuccess: invalidateStrategies });
  const disableMut = useMutation({ mutationFn: (name: string) => adminApi.disableStrategy(name), onSuccess: invalidateStrategies });
  const pauseMut = useMutation({ mutationFn: adminApi.pauseTrading });
  const resumeMut = useMutation({ mutationFn: adminApi.resumeTrading });
  const killMut = useMutation({ mutationFn: adminApi.killSwitch, onSuccess: () => setKillDialog(false) });
  const riskMut = useMutation({ mutationFn: ({ target, value }: { target: string; value: string }) => adminApi.updateRiskLimit(target, value) });

  if (role !== 'Admin') return <Typography color="error" sx={{ mt: 4, textAlign: 'center' }}>Access Denied — Admin role required.</Typography>;
  if (strategies.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>Admin Console</Typography>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>Strategy Controls</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {(strategies.data ?? []).map((s) => (
              <Box key={s.name} sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography variant="body2" sx={{ flex: 1 }}>{s.name}</Typography>
                <Chip label={s.isActive ? 'Active' : 'Inactive'} size="small"
                  sx={{ bgcolor: s.isActive ? '#1b5e2066' : '#42424266', color: s.isActive ? '#4caf50' : '#bdbdbd' }} />
                <Button size="small" variant="outlined" color="success" disabled={s.isActive || enableMut.isPending}
                  onClick={() => enableMut.mutate(s.name)}>Enable</Button>
                <Button size="small" variant="outlined" color="error" disabled={!s.isActive || disableMut.isPending}
                  onClick={() => disableMut.mutate(s.name)}>Disable</Button>
              </Box>
            ))}
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>Trading Controls</Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button variant="outlined" color="warning" disabled={pauseMut.isPending} onClick={() => pauseMut.mutate()}>Pause Trading</Button>
            <Button variant="outlined" color="success" disabled={resumeMut.isPending} onClick={() => resumeMut.mutate()}>Resume Trading</Button>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>Risk Limits</Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <TextField size="small" label="Max Drawdown %" value={maxDrawdown} onChange={(e) => setMaxDrawdown(e.target.value)} sx={{ width: 180 }} />
            <Button variant="outlined" disabled={!maxDrawdown || riskMut.isPending}
              onClick={() => riskMut.mutate({ target: 'maxDrawdownPct', value: maxDrawdown })}>Update</Button>
            <Divider orientation="vertical" flexItem />
            <TextField size="small" label="Max Leverage" value={maxLeverage} onChange={(e) => setMaxLeverage(e.target.value)} sx={{ width: 180 }} />
            <Button variant="outlined" disabled={!maxLeverage || riskMut.isPending}
              onClick={() => riskMut.mutate({ target: 'maxLeverage', value: maxLeverage })}>Update</Button>
          </Box>
        </CardContent>
      </Card>

      <Card sx={{ border: '1px solid #b71c1c' }}>
        <CardContent>
          <Typography variant="subtitle1" color="error" sx={{ fontWeight: 600, mb: 1 }}>Emergency</Typography>
          <Button variant="contained" color="error" onClick={() => setKillDialog(true)}>Kill Switch</Button>
        </CardContent>
      </Card>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Audit Log</Typography>
        <Box className="ag-theme-balham-dark" sx={{ height: 280 }}>
          <AgGridReact theme="legacy" rowData={audit.data ?? []} columnDefs={auditCols}
            defaultColDef={{ sortable: true, resizable: true }} />
        </Box>
      </Box>

      <Dialog open={killDialog} onClose={() => setKillDialog(false)}>
        <DialogTitle>Confirm Kill Switch</DialogTitle>
        <DialogContent>
          <DialogContentText>This will immediately halt all trading. Are you absolutely sure?</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKillDialog(false)}>Cancel</Button>
          <Button color="error" variant="contained" disabled={killMut.isPending} onClick={() => killMut.mutate()}>
            {killMut.isPending ? 'Executing…' : 'Confirm Kill Switch'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
