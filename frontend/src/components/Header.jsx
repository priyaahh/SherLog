import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { getHealth } from '../services/api';

export default function Header() {
  const location = useLocation();
  const [backendHealthy, setBackendHealthy] = useState(null);

  useEffect(() => {
    let isMounted = true;
    getHealth()
      .then((res) => {
        if (isMounted) setBackendHealthy(res?.status === 'healthy');
      })
      .catch(() => {
        if (isMounted) setBackendHealthy(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <header className="terminal-header">
      <div className="brand-section">
        <span className="brand-prompt">sherlog:~$</span>
        <Link to="/" style={{ textDecoration: 'none' }}>
          <span className="brand-title">./incident-ops</span>
        </Link>
        <span className="brand-tag">v1.0.0</span>
      </div>

      <nav className="nav-links">
        <Link
          to="/"
          className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
        >
          [DASHBOARD]
        </Link>
        <Link
          to="/incidents/new"
          className={`nav-link ${location.pathname === '/incidents/new' ? 'active' : ''}`}
        >
          [+ NEW INCIDENT]
        </Link>

        {backendHealthy !== null && (
          <span style={{ fontSize: '11px', color: backendHealthy ? '#22c55e' : '#ef4444' }}>
            ● API: {backendHealthy ? 'ONLINE' : 'OFFLINE'}
          </span>
        )}
      </nav>
    </header>
  );
}
