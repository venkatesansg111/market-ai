import React, { useState } from 'react';
import {
  AppBar, Box, Divider, Drawer, IconButton,
  List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Toolbar, Tooltip, Typography, useTheme,
} from '@mui/material';
import {
  AccountBalance, Assessment, BarChart,
  Dashboard, HealthAndSafety, Logout,
  Menu, Notifications, PlayArrow, Security, ShoppingCart, TrendingUp,
  CandlestickChart,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../store';
import { logout } from '../store/authSlice';

const DRAWER_WIDTH = 220;

const navItems = [
  { label: 'Dashboard',    path: '/',           icon: <Dashboard /> },
  { label: 'Market',       path: '/market',     icon: <TrendingUp /> },
  { label: 'Options Chain',path: '/options',    icon: <CandlestickChart /> },
  { label: 'Strategies',   path: '/strategies', icon: <Assessment /> },
  { label: 'Risk',         path: '/risk',       icon: <Security /> },
  { label: 'Orders',       path: '/orders',     icon: <ShoppingCart /> },
  { label: 'Explainability', path: '/explain',  icon: <BarChart /> },
  { label: 'Replay',       path: '/replay',     icon: <PlayArrow /> },
  { label: 'Alerts',       path: '/alerts',     icon: <Notifications /> },
  { label: 'System Health',path: '/health',     icon: <HealthAndSafety /> },
  { label: 'Admin',        path: '/admin',      icon: <AccountBalance />,  roles: ['Admin'] },
];

interface LayoutProps { children: React.ReactNode; }

export default function Layout({ children }: LayoutProps) {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useAppDispatch();
  const { username, role } = useAppSelector((s) => s.auth);
  const [mobileOpen, setMobileOpen] = useState(false);

  const visibleItems = navItems.filter(
    (item) => !item.roles || item.roles.includes(role ?? '')
  );

  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Toolbar>
        <Typography variant="h6" noWrap sx={{ color: theme.palette.primary.main, fontWeight: 700 }}>
          TradingTerminal
        </Typography>
      </Toolbar>
      <Divider />
      <List dense sx={{ flex: 1 }}>
        {visibleItems.map(({ label, path, icon }) => (
          <ListItem key={path} disablePadding>
            <ListItemButton
              selected={location.pathname === path}
              onClick={() => { navigate(path); setMobileOpen(false); }}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: `${theme.palette.primary.main}22`,
                  borderRight: `3px solid ${theme.palette.primary.main}`,
                },
              }}
            >
              <ListItemIcon sx={{ minWidth: 36, color: location.pathname === path ? theme.palette.primary.main : 'inherit' }}>
                {icon}
              </ListItemIcon>
              <ListItemText primary={label} slotProps={{ primary: { sx: { fontSize: 13 } } }} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Divider />
      <Box sx={{ p: 1.5 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{username}</Typography>
        <Typography variant="caption" color="primary">{role}</Typography>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="fixed" sx={{ zIndex: theme.zIndex.drawer + 1, bgcolor: 'background.paper', borderBottom: '1px solid rgba(255,255,255,0.08)' }} elevation={0}>
        <Toolbar variant="dense">
          <IconButton edge="start" sx={{ mr: 1, display: { md: 'none' } }} onClick={() => setMobileOpen(true)}>
            <Menu />
          </IconButton>
          <Typography variant="body2" sx={{ flex: 1, color: 'text.secondary' }}>
            Phase 11 — Trading Terminal
          </Typography>
          <Tooltip title="Logout">
            <IconButton size="small" onClick={() => { dispatch(logout()); navigate('/login'); }}>
              <Logout fontSize="small" />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{ display: { xs: 'none', md: 'block' }, width: DRAWER_WIDTH, flexShrink: 0, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' } }}
      >
        {drawerContent}
      </Drawer>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { width: DRAWER_WIDTH } }}
      >
        {drawerContent}
      </Drawer>

      <Box component="main" sx={{ flex: 1, ml: { md: `${DRAWER_WIDTH}px` }, p: 2, mt: 6, overflow: 'auto' }}>
        {children}
      </Box>
    </Box>
  );
}
