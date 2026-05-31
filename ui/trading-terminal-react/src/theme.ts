import { createTheme } from '@mui/material/styles';

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary:   { main: '#00d4ff' },
    secondary: { main: '#ff6b35' },
    success:   { main: '#00e676' },
    error:     { main: '#ff1744' },
    warning:   { main: '#ffc107' },
    background: {
      default: '#0a0e1a',
      paper:   '#111827',
    },
    text: {
      primary:   '#e2e8f0',
      secondary: '#94a3b8',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto Mono", monospace',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none', border: '1px solid rgba(255,255,255,0.08)' },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { backgroundImage: 'none', border: '1px solid rgba(255,255,255,0.08)' },
      },
    },
  },
});
