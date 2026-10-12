import React from 'react';

export default function SeverityBadge({ severity }) {
  const sev = (severity || 'medium').toLowerCase();
  
  const classMap = {
    critical: 'badge badge-critical',
    high: 'badge badge-high',
    medium: 'badge badge-medium',
    low: 'badge badge-low',
  };

  const label = `[${sev.toUpperCase()}]`;

  return (
    <span className={classMap[sev] || 'badge badge-medium'}>
      {label}
    </span>
  );
}
