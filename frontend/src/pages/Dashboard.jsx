import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getIncidents } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import StatusBadge from '../components/StatusBadge';

const PAGE_SIZE = 15;

export default function Dashboard() {
  const [incidents, setIncidents] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchList = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getIncidents({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        status: statusFilter,
        severity: severityFilter,
      });
      setIncidents(data.incidents || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || 'Failed to fetch incident directory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, [page, statusFilter, severityFilter]);

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  const formatDate = (isoStr) => {
    if (!isoStr) return 'N/A';
    try {
      const d = new Date(isoStr);
      return d.toISOString().replace('T', ' ').substring(0, 19);
    } catch {
      return isoStr;
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <h1 className="card-title" style={{ fontSize: '15px' }}>
              INCIDENT DIRECTORY [TOTAL: {total}]
            </h1>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <Link to="/incidents/new" className="btn btn-primary" id="btn-create-incident">
              + NEW INCIDENT
            </Link>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>STATUS:</span>
            <select
              className="form-select"
              style={{ width: 'auto', padding: '6px 10px' }}
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="">ALL STATUSES</option>
              <option value="open">OPEN</option>
              <option value="investigating">INVESTIGATING</option>
              <option value="investigated">INVESTIGATED</option>
              <option value="resolved">RESOLVED</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>SEVERITY:</span>
            <select
              className="form-select"
              style={{ width: 'auto', padding: '6px 10px' }}
              value={severityFilter}
              onChange={(e) => {
                setSeverityFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="">ALL SEVERITIES</option>
              <option value="critical">CRITICAL</option>
              <option value="high">HIGH</option>
              <option value="medium">MEDIUM</option>
              <option value="low">LOW</option>
            </select>
          </div>

          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '12px' }}
            onClick={fetchList}
          >
            REFRESH
          </button>
        </div>

        {error && <div className="alert-box alert-error">{error}</div>}

        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            $ querying incident store...
          </div>
        ) : incidents.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            No incidents found matching query criteria.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="terminal-table" id="incidents-table">
              <thead>
                <tr>
                  <th style={{ width: '130px' }}>STATUS</th>
                  <th style={{ width: '120px' }}>SEVERITY</th>
                  <th>TITLE</th>
                  <th style={{ width: '160px' }}>SERVICE</th>
                  <th style={{ width: '180px' }}>CREATED_AT</th>
                  <th style={{ width: '100px', textAlign: 'right' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => (
                  <tr key={inc.id} id={`incident-row-${inc.id}`}>
                    <td>
                      <StatusBadge status={inc.status} />
                    </td>
                    <td>
                      <SeverityBadge severity={inc.severity} />
                    </td>
                    <td>
                      <Link
                        to={`/incidents/${inc.id}`}
                        style={{ color: 'var(--text-primary)', fontWeight: 500 }}
                      >
                        {inc.title}
                      </Link>
                    </td>
                    <td>
                      <span style={{ color: 'var(--text-secondary)' }}>{inc.service_name}</span>
                    </td>
                    <td>
                      <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                        {formatDate(inc.created_at)}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Link
                        to={`/incidents/${inc.id}`}
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '11px' }}
                      >
                        VIEW &gt;
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="pagination">
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            PAGE {page + 1} OF {totalPages}
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 10px', fontSize: '12px' }}
              disabled={page === 0 || loading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              &lt; PREV
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 10px', fontSize: '12px' }}
              disabled={page >= totalPages - 1 || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              NEXT &gt;
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
