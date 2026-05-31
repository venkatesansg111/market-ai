import { useState } from 'react';
import { Box, Card, CardContent, Chip, CircularProgress, Step, StepContent, StepLabel, Stepper, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { explainApi } from '../api/endpoints';

interface TradeExplain {
  tradeId: string;
  symbol: string;
  strategyName: string;
  currentRegime: string;
  confidenceScore: number;
  riskScore: number;
  riskDecision: string;
  positionSizeReason: string;
  executionReason: string;
  decisionChain: { step: string; description: string }[];
}

interface TradeSummary {
  tradeId: string;
  symbol: string;
  strategyName: string;
  entryTime: string;
}

export default function ExplainPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const list = useQuery({ queryKey: ['explainAll'], queryFn: explainApi.all });
  const detail = useQuery({
    queryKey: ['explainTrade', selectedId],
    queryFn: () => explainApi.trade(selectedId!),
    enabled: !!selectedId,
  });

  if (list.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>;
  if (list.isError) return <Typography color="error">Error loading explanations</Typography>;

  const trades: TradeSummary[] = list.data ?? [];
  const d: TradeExplain | null = detail.data ?? null;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Trade Explainability</Typography>
      <Box sx={{ display: 'flex', gap: 2, height: 'calc(100vh - 150px)' }}>
        <Box sx={{ width: 260, overflowY: 'auto', bgcolor: 'background.paper', borderRadius: 1, p: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>Select a trade</Typography>
          {trades.map((t) => (
            <Box key={t.tradeId} onClick={() => setSelectedId(t.tradeId)}
              sx={{ p: 1.5, borderRadius: 1, cursor: 'pointer', mb: 0.5,
                bgcolor: selectedId === t.tradeId ? 'primary.dark' : 'transparent',
                '&:hover': { bgcolor: 'action.hover' } }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{t.symbol}</Typography>
              <Typography variant="caption" color="text.secondary">{t.strategyName}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {t.entryTime ? new Date(t.entryTime).toLocaleString() : ''}
              </Typography>
            </Box>
          ))}
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto' }}>
          {!selectedId && <Typography color="text.secondary" sx={{ mt: 4, textAlign: 'center' }}>Select a trade to view its explanation</Typography>}
          {detail.isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>}
          {d && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 1 }}>
                    <Typography variant="h6">{d.symbol}</Typography>
                    <Chip label={d.strategyName} size="small" color="primary" />
                    <Chip label={d.currentRegime} size="small" variant="outlined" />
                  </Box>
                  <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    {[
                      ['Trade ID', d.tradeId],
                      ['Confidence', `${(d.confidenceScore * 100).toFixed(1)}%`],
                      ['Risk Score', d.riskScore?.toFixed(2)],
                      ['Risk Decision', d.riskDecision],
                    ].map(([label, val]) => (
                      <Box key={label as string}>
                        <Typography variant="caption" color="text.secondary">{label}</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
                      </Box>
                    ))}
                  </Box>
                </CardContent>
              </Card>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Position Size Reason</Typography>
                  <Typography variant="body2" color="text.secondary">{d.positionSizeReason}</Typography>
                  <Typography variant="subtitle2" sx={{ mt: 1.5, mb: 0.5 }}>Execution Reason</Typography>
                  <Typography variant="body2" color="text.secondary">{d.executionReason}</Typography>
                </CardContent>
              </Card>
              {d.decisionChain?.length > 0 && (
                <Card>
                  <CardContent>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>Decision Chain</Typography>
                    <Stepper orientation="vertical" nonLinear activeStep={-1}>
                      {d.decisionChain.map((step, i) => (
                        <Step key={i} active>
                          <StepLabel>{step.step}</StepLabel>
                          <StepContent><Typography variant="caption" color="text.secondary">{step.description}</Typography></StepContent>
                        </Step>
                      ))}
                    </Stepper>
                  </CardContent>
                </Card>
              )}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
