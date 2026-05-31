import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import { darkTheme } from '../theme';
import StatCard from '../components/StatCard';

const wrap = (ui: React.ReactElement) =>
  render(<ThemeProvider theme={darkTheme}>{ui}</ThemeProvider>);

describe('StatCard', () => {
  it('renders title and value', () => {
    wrap(<StatCard title="Total Equity" value="₹1,024,500" />);
    expect(screen.getByText('Total Equity')).toBeInTheDocument();
    expect(screen.getByText('₹1,024,500')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    wrap(<StatCard title="PnL" value="+2,150" subtitle="Today" />);
    expect(screen.getByText('Today')).toBeInTheDocument();
  });

  it('renders without subtitle when not provided', () => {
    wrap(<StatCard title="Cash" value="312,000" />);
    expect(screen.getByText('Cash')).toBeInTheDocument();
    expect(screen.getByText('312,000')).toBeInTheDocument();
    expect(screen.queryByText('Today')).toBeNull();
  });
});
