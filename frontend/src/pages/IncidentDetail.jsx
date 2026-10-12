import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  getIncident,
  getIncidentLogs,
  uploadIncidentLogs,
  triggerInvestigation,
  getInvestigationStatus,
  getIncidentReport,
  updateIncidentStatus,
} from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import StatusBadge from '../components/StatusBadge';

export default function IncidentDetail() {
  const { id } = useParams();

  const [incident, setIncident] = useState(null);
  const [logs, setLogs] = useState(null);
  const [investigation, setInvestigation] = useState(null);
  const [hasReport, setHasReport] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [resolving, setResolving] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const fileInputRef = useRef(null);
  const pollTimerRef = useRef(null);

  // Load incident core details
  const fetchIncidentDetails = useCallback(async () => {
    try {
      const data = await getIncident(id);
      setIncident(data);
      return data;
    } catch (err) {
      setError(err.message || 'Failed to load incident');
      return null;
    }
  }, [id]);

  // Load log file
  const fetchLogs = useCallback(async () => {
    try {
      const logData = await getIncidentLogs(id);
      setLogs(logData);
    } catch {
      // 404 indicates no logs uploaded yet
      setLogs(null);
    }
  }, [id]);

  // Load investigation status
  const fetchInvestigation = useCallback(async () => {
    try {
      const invData = await getInvestigationStatus(id);
      setInvestigation(invData);
      return invData;
    } catch {
      // 404 indicates investigation not started
      setInvestigation(null);
      return null;
    }
  }, [id]);

  // Check if report is generated
  const checkReport = useCallback(async () => {
    try {
      const rep = await getIncidentReport(id);
      if (rep && rep.id) {
        setHasReport(true);
      }
    } catch {
      setHasReport(false);
    }
  }, [id]);

  // Initial load
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError('');

    Promise.all([fetchIncidentDetails(), fetchLogs(), fetchInvestigation(), checkReport()])
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [id, fetchIncidentDetails, fetchLogs, fetchInvestigation, checkReport]);

  // Auto-polling every 5 seconds when investigation is in_progress
  const isInvestigating =
    investigation?.status === 'in_progress' || incident?.status === 'investigating';

  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (isInvestigating) {
      pollTimerRef.current = setInterval(async () => {
        const [inv, inc] = await Promise.all([fetchInvestigation(), fetchIncidentDetails()]);

        if (inv && (inv.status === 'completed' || inv.status === 'failed')) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          if (inv.status === 'completed') {
            setNotice('[COMPLETED] AI root cause analysis is finished.');
            checkReport();
          } else {
            setError(`[FAILED] Investigation terminated: ${inv.errors?.join(', ') || 'Unknown error'}`);
          }
        }
      }, 5000);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [isInvestigating, fetchInvestigation, fetchIncidentDetails, checkReport]);

  // Action: File Selection
  const handleFileChange = (e) => {
    setError('');
    setNotice('');
    const file = e.target.files?.[0];
    if (!file) return;

    const allowed = ['.log', '.txt', '.json'];
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
      setError(`Unsupported file extension '${ext}'. Allowed: .log, .txt, .json`);
      setSelectedFile(null);
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError(`File size exceeds 5 MB limit (${(file.size / 1024 / 1024).toFixed(2)} MB).`);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  // Action: Upload File
  const handleUploadSubmit = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError('');
    setNotice('');

    try {
      await uploadIncidentLogs(id, selectedFile);
      setNotice(`[SUCCESS] File '${selectedFile.name}' ingested successfully.`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await fetchLogs();
    } catch (err) {
      setError(err.message || 'Log file upload failed.');
    } finally {
      setUploading(false);
    }
  };

  // Action: Trigger Investigation
  const handleTriggerInvestigation = async () => {
    if (!logs) {
      setError('Cannot trigger investigation without uploaded log records.');
      return;
    }
    setTriggering(true);
    setError('');
    setNotice('');

    try {
      const res = await triggerInvestigation(id);
      setNotice(`[ACCEPTED] AI investigation dispatched (${res.investigation_id || 'active'}). Polling status...`);
      await Promise.all([fetchInvestigation(), fetchIncidentDetails()]);
    } catch (err) {
      setError(err.message || 'Failed to dispatch AI investigation.');
    } finally {
      setTriggering(false);
    }
  };

  // Action: Resolve Incident
  const handleResolve = async () => {
    setResolving(true);
    setError('');
    setNotice('');

    try {
      await updateIncidentStatus(id, 'resolved');
      setNotice('[RESOLVED] Incident marked as resolved.');
      await fetchIncidentDetails();
    } catch (err) {
      setError(err.message || 'Failed to resolve incident.');
    } finally {
      setResolving(false);
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return 'N/A';
    try {
      return new Date(isoStr).toISOString().replace('T', ' ').substring(0, 19);
    } catch {
      return isoStr;
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
        $ querying incident [{id}]...
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="card">
        <div className="alert-box alert-error">Incident not found (ID: {id})</div>
        <Link to="/" className="btn btn-secondary">
          &lt; BACK TO DASHBOARD
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Top Navigation */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link to="/" className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '12px' }}>
          &lt; BACK TO DIRECTORY
        </Link>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          REF: #{incident.id}
        </span>
      </div>

      {/* Notifications */}
      {error && (
        <div className="alert-box alert-error" id="incident-error-banner">
          <span>[ERROR] {error}</span>
          <button
            onClick={() => setError('')}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            [X]
          </button>
        </div>
      )}

      {notice && (
        <div className="alert-box alert-success" id="incident-notice-banner">
          <span>{notice}</span>
          <button
            onClick={() => setNotice('')}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            [X]
          </button>
        </div>
      )}

      {/* Primary Incident Details Card */}
      <div className="card" id="card-incident-summary">
        <div className="card-header incident-card-header">
          <div className="incident-header-title-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px', flexWrap: 'wrap' }}>
              <StatusBadge status={incident.status} />
              <SeverityBadge severity={incident.severity} />
              <span style={{ color: 'var(--accent-teal)', fontSize: '12px' }}>
                SERVICE: {incident.service_name}
              </span>
            </div>
            <h1 className="card-title" style={{ fontSize: '17px', color: 'var(--text-primary)', wordBreak: 'break-word' }}>
              {incident.title}
            </h1>
          </div>

          {/* Action Buttons Toolbar */}
          <div className="incident-action-buttons">
            {/* View Report Button (highlighted when available) */}
            {(hasReport || investigation?.status === 'completed') && (
              <Link
                to={`/incidents/${incident.id}/report`}
                className="btn btn-primary"
                id="btn-view-report"
              >
                [!] VIEW RCA REPORT
              </Link>
            )}

            {/* Trigger Investigation Button */}
            <button
              type="button"
              className="btn btn-primary"
              id="btn-trigger-investigation"
              disabled={!logs || isInvestigating || triggering}
              onClick={handleTriggerInvestigation}
            >
              {triggering
                ? '$ DISPATCHING...'
                : isInvestigating
                ? '$ INVESTIGATION RUNNING...'
                : 'TRIGGER INVESTIGATION'}
            </button>

            {/* Resolve Incident Button */}
            <button
              type="button"
              className="btn btn-secondary"
              id="btn-resolve-incident"
              disabled={incident.status === 'resolved' || resolving}
              onClick={handleResolve}
            >
              {resolving ? '$ RESOLVING...' : incident.status === 'resolved' ? '[RESOLVED]' : 'RESOLVE INCIDENT'}
            </button>
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="meta-grid">
          <div className="meta-item">
            <div className="meta-label">TARGET SERVICE</div>
            <div className="meta-value">{incident.service_name}</div>
          </div>
          <div className="meta-item">
            <div className="meta-label">CURRENT STATUS</div>
            <div className="meta-value">
              <StatusBadge status={incident.status} />
            </div>
          </div>
          <div className="meta-item">
            <div className="meta-label">SEVERITY TIER</div>
            <div className="meta-value">
              <SeverityBadge severity={incident.severity} />
            </div>
          </div>
          <div className="meta-item">
            <div className="meta-label">DISPATCH TIMESTAMP</div>
            <div className="meta-value">{formatDate(incident.created_at)}</div>
          </div>
          <div className="meta-item">
            <div className="meta-label">LAST UPDATED</div>
            <div className="meta-value">{formatDate(incident.updated_at)}</div>
          </div>
        </div>

        {/* Description Section */}
        <div style={{ marginTop: '16px' }}>
          <div className="meta-label" style={{ marginBottom: '8px' }}>SYMPTOM TELEMETRY & DESCRIPTION</div>
          <div
            style={{
              backgroundColor: 'var(--bg-main)',
              border: '1px solid var(--border-color)',
              padding: '12px 14px',
              borderRadius: '2px',
              color: 'var(--text-primary)',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}
          >
            {incident.description}
          </div>
        </div>
      </div>

      {/* Investigation Status Card */}
      <div className="card" id="card-investigation-status">
        <div className="card-header">
          <div className="card-title">AI INVESTIGATION PIPELINE</div>
          <div>
            {investigation?.status ? (
              <StatusBadge status={investigation.status} />
            ) : isInvestigating ? (
              <StatusBadge status="in_progress" />
            ) : (
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>[NOT_STARTED]</span>
            )}
          </div>
        </div>

        {!investigation && !isInvestigating ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            No investigation run recorded. Upload logs and trigger investigation above.
          </div>
        ) : (
          <div>
            <div className="meta-grid" style={{ marginBottom: '12px' }}>
              <div className="meta-item">
                <div className="meta-label">INVESTIGATION ID</div>
                <div className="meta-value" style={{ fontSize: '12px' }}>
                  {investigation?.id || (isInvestigating ? 'DISPATCHED' : 'N/A')}
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">STATUS</div>
                <div className="meta-value">
                  <StatusBadge status={investigation?.status || (isInvestigating ? 'in_progress' : 'not_started')} />
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">LINES ANALYZED</div>
                <div className="meta-value">
                  {investigation?.logs_analyzed_count || '0'} lines
                  {investigation?.logs_truncated && (
                    <span style={{ color: 'var(--sev-medium)', marginLeft: '8px', fontSize: '11px' }}>
                      [CAPPED AT 500]
                    </span>
                  )}
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">START TIME</div>
                <div className="meta-value">
                  {investigation?.started_at ? formatDate(investigation.started_at) : 'N/A'}
                </div>
              </div>
            </div>

            {isInvestigating && (
              <div
                style={{
                  padding: '10px 14px',
                  border: '1px solid var(--accent-teal)',
                  backgroundColor: 'var(--bg-main)',
                  borderRadius: '2px',
                  color: 'var(--accent-teal)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: '12px',
                }}
              >
                <span className="blink-dot" />
                <span>
                  Investigation pipeline in progress... auto-polling status every 5 seconds.
                </span>
              </div>
            )}

            {investigation.truncation_note && (
              <div style={{ fontSize: '12px', color: 'var(--sev-medium)', marginTop: '8px' }}>
                Note: {investigation.truncation_note}
              </div>
            )}

            {investigation.errors && investigation.errors.length > 0 && (
              <div style={{ marginTop: '10px' }}>
                <div className="meta-label" style={{ color: 'var(--sev-critical)' }}>PIPELINE WARNINGS / ERRORS:</div>
                <div className="terminal-viewer" style={{ maxHeight: '120px' }}>
                  {investigation.errors.map((err, i) => (
                    <div key={i} style={{ color: 'var(--sev-critical)' }}>
                      - {err}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {investigation.status === 'completed' && (
              <div style={{ marginTop: '12px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{ color: 'var(--accent-teal)', fontSize: '13px' }}>
                  Root cause analysis generated.
                </span>
                <Link to={`/incidents/${incident.id}/report`} className="btn btn-primary" style={{ padding: '4px 12px' }}>
                  OPEN REPORT &gt;
                </Link>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Log Ingestion & Terminal Viewer Card */}
      <div className="card" id="card-logs-viewer">
        <div className="card-header">
          <div>
            <span className="card-title">TELEMETRY & LOG STREAM</span>
            {logs && (
              <span style={{ marginLeft: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>
                FILE: {logs.filename} ({logs.total_entries} entries)
              </span>
            )}
          </div>

          {/* Log File Picker & Uploader */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <input
              type="file"
              ref={fileInputRef}
              accept=".log,.txt,.json"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              id="file-input-logs"
            />

            <button
              type="button"
              className="btn btn-secondary"
              id="btn-select-file"
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              disabled={uploading}
            >
              {selectedFile ? `SELECTED: ${selectedFile.name}` : 'CHOOSE LOG FILE'}
            </button>

            {selectedFile && (
              <button
                type="button"
                className="btn btn-primary"
                id="btn-upload-file"
                disabled={uploading}
                onClick={handleUploadSubmit}
              >
                {uploading ? '$ UPLOADING...' : 'UPLOAD LOG'}
              </button>
            )}
          </div>
        </div>

        {!logs ? (
          <div style={{ padding: '36px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            <p>No log records attached to this incident yet.</p>
            <p style={{ marginTop: '8px', fontSize: '12px' }}>
              Select a .log, .txt, or .json file (&lt; 5MB) and click Upload to enable AI root cause analysis.
            </p>
          </div>
        ) : (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
              <span>RAW LOG TELEMETRY OUTPUT [{logs.total_entries} LINES]</span>
              <span>INGESTED AT: {formatDate(logs.uploaded_at)}</span>
            </div>

            <div className="terminal-viewer" id="log-terminal-output">
              {logs.raw_content && logs.raw_content.length > 0 ? (
                logs.raw_content.map((line, idx) => (
                  <div key={idx} className="log-line">
                    <span className="log-line-num">{idx + 1}</span>
                    <span className="log-line-content">{line}</span>
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--text-muted)' }}>[Empty log content]</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
