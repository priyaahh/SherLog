import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { createIncident } from '../services/api';

export default function CreateIncident() {
  const navigate = useNavigate();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [serviceName, setServiceName] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!title.trim() || title.trim().length < 3) {
      setError('Title must be at least 3 characters.');
      return;
    }
    if (!serviceName.trim() || serviceName.trim().length < 2) {
      setError('Service name must be at least 2 characters.');
      return;
    }
    if (!description.trim() || description.trim().length < 5) {
      setError('Description must be at least 5 characters.');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim(),
        service_name: serviceName.trim(),
        severity,
      };

      const res = await createIncident(payload);
      if (res && res.id) {
        navigate(`/incidents/${res.id}`);
      } else {
        navigate('/');
      }
    } catch (err) {
      setError(err.message || 'Failed to initialize new incident.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <Link to="/" className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '12px' }}>
          &lt; BACK TO DIRECTORY
        </Link>
      </div>

      <div className="card">
        <div className="card-header">
          <h1 className="card-title" style={{ fontSize: '15px' }}>
            INITIATE INCIDENT RECORD [POST /incidents]
          </h1>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            $ sh-cli incident:create
          </span>
        </div>

        {error && (
          <div className="alert-box alert-error" id="form-error-banner">
            <span>[ERROR] {error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="incident-title">
              INCIDENT TITLE *
            </label>
            <input
              id="incident-title"
              type="text"
              className="form-input"
              placeholder="e.g. Postgres Connection Pool Exhaustion"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="incident-service">
                SERVICE NAME *
              </label>
              <input
                id="incident-service"
                type="text"
                className="form-input"
                placeholder="e.g. auth-api, billing-worker"
                value={serviceName}
                onChange={(e) => setServiceName(e.target.value)}
                disabled={loading}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="incident-severity">
                SEVERITY LEVEL *
              </label>
              <select
                id="incident-severity"
                className="form-select"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                disabled={loading}
              >
                <option value="low">LOW</option>
                <option value="medium">MEDIUM</option>
                <option value="high">HIGH</option>
                <option value="critical">CRITICAL</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="incident-desc">
              SYMPTOM DESCRIPTION *
            </label>
            <textarea
              id="incident-desc"
              className="form-textarea"
              rows={5}
              placeholder="Describe observed failure symptoms, alerts triggered, or latency spikes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
            <button
              type="submit"
              className="btn btn-primary"
              id="btn-submit-incident"
              disabled={loading}
            >
              {loading ? '$ DISPATCHING...' : 'DISPATCH INCIDENT RECORD'}
            </button>
            <Link
              to="/"
              className="btn btn-secondary"
              id="btn-cancel"
            >
              CANCEL
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
