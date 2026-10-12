import React from 'react';

export default function StatusBadge({ status }) {
  const norm = (status || 'open').toLowerCase();

  if (norm === 'in_progress' || norm === 'investigating') {
    return (
      <span className="badge badge-investigating">
        <span className="blink-dot" />
        [IN_PROGRESS]
      </span>
    );
  }

  if (norm === 'completed') {
    return (
      <span className="badge badge-investigated">
        [COMPLETED]
      </span>
    );
  }

  if (norm === 'investigated') {
    return (
      <span className="badge badge-investigated">
        [INVESTIGATED]
      </span>
    );
  }

  if (norm === 'resolved') {
    return (
      <span className="badge badge-resolved">
        [RESOLVED]
      </span>
    );
  }

  if (norm === 'failed') {
    return (
      <span className="badge badge-failed">
        [FAILED]
      </span>
    );
  }

  if (norm === 'not_started') {
    return (
      <span className="badge badge-open">
        [NOT_STARTED]
      </span>
    );
  }

  return (
    <span className="badge badge-open">
      [OPEN]
    </span>
  );
}
