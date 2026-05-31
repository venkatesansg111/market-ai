import React from 'react';
import { Box, Card, CardContent, Typography } from '@mui/material';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
  icon?: React.ReactNode;
}

export default function StatCard({ title, value, subtitle, color, icon }: StatCardProps) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{title}</Typography>
            <Typography variant="h5" sx={{ color: color ?? 'text.primary', fontWeight: 700, mt: 0.5 }}>
              {value}
            </Typography>
            {subtitle && (
              <Typography variant="caption" color="text.secondary">{subtitle}</Typography>
            )}
          </Box>
          {icon && (
            <Box sx={{ color: color ?? 'primary.main', opacity: 0.7 }}>{icon}</Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}
