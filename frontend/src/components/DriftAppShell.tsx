import React, { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Gauge, History, House, Map, Menu, X } from 'lucide-react';
import { DRIFT_NAV_ITEMS } from '../config/driftRouteConfig';

export const DriftAppShell: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 900);

  useEffect(() => {
<<<<<<< HEAD
    const onResize = () => setIsMobile(window.innerWidth <= 900);
=======
    const onResize = () => {
      const mobile = window.innerWidth <= 900;
      setIsMobile(mobile);
      if (!mobile) {
        setOpen(false);
      }
    };
>>>>>>> 03bede4b76d58f688eb646a8334761916b600cbb
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

<<<<<<< HEAD
  useEffect(() => {
    if (!isMobile) {
      setOpen(false);
    }
  }, [isMobile]);

=======
>>>>>>> 03bede4b76d58f688eb646a8334761916b600cbb
  const mobileItems = [
    { label: 'Map', to: '/drift', icon: Map, activePrefixes: ['/drift'] },
    { label: 'History', to: '/drift/history', icon: History, activePrefixes: ['/drift/history'] },
    { label: 'Intel', to: '/drift/dashboard', icon: Gauge, activePrefixes: ['/drift/dashboard'] },
  ];

  return (
    <div style={{ display: 'flex', minHeight: '100vh', width: '100%', position: 'relative' }}>
      {isMobile && (
        <button
          onClick={() => setOpen((prev) => !prev)}
          style={{
            position: 'fixed',
            top: 14,
            left: 12,
            zIndex: 120,
            width: 40,
            height: 40,
            borderRadius: 10,
            border: '1px solid #3f4959',
            background: '#2a3340',
            color: '#d7e2ef',
            display: 'grid',
            placeItems: 'center',
            cursor: 'pointer',
            boxShadow: '0 8px 22px rgba(0,0,0,0.35)',
          }}
          aria-label="Toggle D.R.I.F.T. navigation"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      )}

      {isMobile && open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.45)',
            zIndex: 90,
          }}
        />
      )}

      <aside
        style={{
          width: isMobile ? 240 : open ? 220 : 72,
          transition: isMobile ? 'transform 0.2s ease' : 'width 0.2s ease',
          background: '#202631',
          borderRight: '1px solid #38404d',
          padding: '16px 10px 18px',
          boxSizing: 'border-box',
          position: isMobile ? 'fixed' : 'sticky',
          top: 0,
          left: 0,
          height: '100vh',
          transform: isMobile ? (open ? 'translateX(0)' : 'translateX(-105%)') : 'none',
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <button
          onClick={() => setOpen((prev) => !prev)}
          style={{
            width: '100%',
            height: 42,
            borderRadius: 10,
            border: '1px solid #3f4959',
            background: '#2a3340',
            color: '#cbd5e1',
            display: 'flex',
            alignItems: 'center',
            justifyContent: open || isMobile ? 'space-between' : 'center',
            padding: open || isMobile ? '0 10px' : 0,
            cursor: 'pointer',
            marginBottom: 16,
            opacity: isMobile ? 0 : 1,
            pointerEvents: isMobile ? 'none' : 'auto',
          }}
        >
          {(open || isMobile) && <span style={{ fontSize: 12, letterSpacing: '0.08em', fontWeight: 700 }}>D.R.I.F.T. NAV</span>}
          <Menu size={16} />
        </button>

        <div style={{ display: 'grid', gap: 12 }}>
          {DRIFT_NAV_ITEMS.map((item) => {
            const active = item.activePrefixes.some((prefix) =>
              prefix === '/drift' ? location.pathname === '/drift' : location.pathname.startsWith(prefix)
            );
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                onClick={() => {
                  navigate(item.to);
                  if (isMobile) setOpen(false);
                }}
                style={{
                  width: '100%',
                  minHeight: 44,
                  borderRadius: 11,
                  border: active ? '1px solid #279a74' : '1px solid #34404f',
                  background: active ? '#1f7a5d' : '#26303d',
                  color: active ? '#eaf8f3' : '#d6dfeb',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: open || isMobile ? 'flex-start' : 'center',
                  gap: 12,
                  padding: open || isMobile ? '0 12px' : 0,
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                <Icon size={16} />
                {(open || isMobile) && <span style={{ fontSize: 13 }}>{item.label}</span>}
              </button>
            );
          })}
        </div>

        <div style={{ marginTop: 'auto' }}>
          <button
            onClick={() => {
              navigate('/');
              if (isMobile) setOpen(false);
            }}
            style={{
              width: '100%',
              minHeight: 44,
              borderRadius: 11,
              border: '1px solid #415063',
              background: '#2a3340',
              color: '#e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: open || isMobile ? 'flex-start' : 'center',
              gap: 12,
              padding: open || isMobile ? '0 12px' : 0,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            <House size={16} />
            {(open || isMobile) && <span style={{ fontSize: 13 }}>Landing</span>}
          </button>
        </div>
      </aside>

      <div style={{ flex: 1, minWidth: 0, paddingBottom: isMobile ? 72 : 0 }}>
        <Outlet />
      </div>

      {isMobile && (
        <nav
          style={{
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            height: 64,
            background: 'rgba(32, 38, 49, 0.96)',
            backdropFilter: 'blur(10px)',
            borderTop: '1px solid #38404d',
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            zIndex: 110,
          }}
        >
          {mobileItems.map((item) => {
            const active = item.activePrefixes.some((prefix) =>
              prefix === '/drift' ? location.pathname === '/drift' : location.pathname.startsWith(prefix)
            );
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                onClick={() => navigate(item.to)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: active ? '#10b981' : '#d7e2ef',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                aria-label={`Open ${item.label}`}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      )}
    </div>
  );
};
