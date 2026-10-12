import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getIncidentReport, getInvestigationStatus, getIncident } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

function extractAnomalySample(anom) {
  if (!anom) return 'N/A';

  let obj = anom;
  if (typeof anom === 'string') {
    try {
      obj = JSON.parse(anom);
    } catch {
      return anom;
    }
  }

  // 1. Check results[0].examples[0]
  if (obj?.results?.[0]?.examples?.[0]) {
    return String(obj.results[0].examples[0]);
  }

  // 2. Check if a string property contains JSON with results[0].examples[0]
  for (const key of ['sample', 'description', 'detail', 'details', 'raw']) {
    if (typeof obj?.[key] === 'string') {
      try {
        const parsed = JSON.parse(obj[key]);
        if (parsed?.results?.[0]?.examples?.[0]) {
          return String(parsed.results[0].examples[0]);
        }
        if (parsed?.examples?.[0]) {
          return String(parsed.examples[0]);
        }
      } catch {
        // Not a JSON string
      }
    }
  }

  // 3. Check examples[0]
  if (Array.isArray(obj?.examples) && obj.examples.length > 0) {
    return String(obj.examples[0]);
  }

  // 4. Check if results[0] is directly a string
  if (Array.isArray(obj?.results) && typeof obj.results[0] === 'string') {
    return String(obj.results[0]);
  }

  // 5. Common text fallback fields (never dump raw JSON)
  if (typeof obj?.sample === 'string') return obj.sample;
  if (typeof obj?.description === 'string') return obj.description;
  if (typeof obj?.line === 'string') return obj.line;
  if (typeof obj?.message === 'string') return obj.message;

  return 'N/A';
}

export default function ReportView() {
  const { id } = useParams();

  const [report, setReport] = useState(null);
  const [investigation, setInvestigation] = useState(null);
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError('');

    Promise.all([
      getIncidentReport(id),
      getInvestigationStatus(id).catch(() => null),
      getIncident(id).catch(() => null),
    ])
      .then(([rep, inv, inc]) => {
        if (!isMounted) return;
        setReport(rep);
        setInvestigation(inv);
        setIncident(inc);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err.message || 'Report not found or not yet generated.');
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [id]);

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
        $ compiling post-incident RCA report for [{id}]...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="card">
        <div className="alert-box alert-error" style={{ marginBottom: '16px' }}>
          {error || 'No report found for this incident.'}
        </div>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '16px', fontSize: '13px' }}>
          A report is automatically generated once an AI investigation run completes successfully.
        </p>
        <Link to={`/incidents/${id}`} className="btn btn-secondary">
          &lt; RETURN TO INCIDENT
        </Link>
      </div>
    );
  }

  const risk = report.risk_assessment || {};
  const anomalies = investigation?.anomalies || [];
  const recommendations = report.recommendations || [];
  const runbooks = investigation?.relevant_runbooks || [];

  return (
    <div>
      {/* Navigation */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link to={`/incidents/${id}`} className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '12px' }}>
          &lt; RETURN TO INCIDENT #{id}
        </Link>
        <span style={{ fontSize: '12px', color: 'var(--accent-teal)' }}>
          REPORT ID: #{report.id}
        </span>
      </div>

      {/* Header Banner */}
      <div className="card">
        <div className="card-header">
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
              INCIDENT POST-MORTEM & ROOT CAUSE ANALYSIS
            </div>
            <h1 className="card-title" style={{ fontSize: '18px' }}>
              {incident?.title || `Incident #${id}`}
            </h1>
          </div>
          <div style={{ textAlign: 'right', fontSize: '12px', color: 'var(--text-muted)' }}>
            <div>SERVICE: <span style={{ color: 'var(--text-primary)' }}>{incident?.service_name || 'N/A'}</span></div>
            <div>COMPILED: {formatDate(report.generated_at)}</div>
          </div>
        </div>

        {/* 1. Root Cause Section */}
        <div style={{ marginBottom: '24px' }}>
          <div className="meta-label" style={{ fontSize: '12px', color: 'var(--accent-teal)', marginBottom: '8px' }}>
            &gt; 01. DETERMINED ROOT CAUSE
          </div>
          <div
            style={{
              backgroundColor: '#050810',
              border: '1px solid var(--border-color)',
              padding: '16px',
              borderRadius: '2px',
              color: 'var(--text-primary)',
              lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
              fontSize: '13px',
            }}
            id="report-root-cause"
          >
            {report.root_cause}
          </div>
        </div>

        {/* 2. Risk Assessment Grid */}
        <div style={{ marginBottom: '24px' }}>
          <div className="meta-label" style={{ fontSize: '12px', color: 'var(--accent-teal)', marginBottom: '8px' }}>
            &gt; 02. RISK & BLAST RADIUS ASSESSMENT
          </div>

          <div className="meta-grid" id="report-risk-grid">
            <div className="meta-item">
              <div className="meta-label">SEVERITY EVALUATION</div>
              <div className="meta-value">
                <SeverityBadge severity={risk.severity || 'medium'} />
              </div>
            </div>

            <div className="meta-item">
              <div className="meta-label">CONFIDENCE METRIC</div>
              <div className="meta-value" style={{ color: 'var(--accent-teal)' }}>
                {typeof risk.confidence === 'number'
                  ? `${(risk.confidence * 100).toFixed(0)}%`
                  : risk.confidence || '90%'}
              </div>
            </div>

            <div className="meta-item">
              <div className="meta-label">BLAST RADIUS</div>
              <div className="meta-value">
                {risk.blast_radius || 'Isolated Service Scope'}
              </div>
            </div>

            {risk.attack_pattern && (
              <div className="meta-item">
                <div className="meta-label">PATTERN / TECHNIQUE</div>
                <div className="meta-value">
                  {risk.attack_pattern}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 3. Actionable Recommendations List */}
        <div style={{ marginBottom: '24px' }}>
          <div className="meta-label" style={{ fontSize: '12px', color: 'var(--accent-teal)', marginBottom: '8px' }}>
            &gt; 03. MITIGATION & REMEDIATION RECOMMENDATIONS
          </div>

          {recommendations.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
              No explicit recommendations returned.
            </div>
          ) : (
            <div
              style={{
                backgroundColor: 'var(--bg-main)',
                border: '1px solid var(--border-color)',
                borderRadius: '2px',
                padding: '12px 16px',
              }}
              id="report-recommendations-list"
            >
              {recommendations.map((rec, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    padding: '8px 0',
                    borderBottom: idx < recommendations.length - 1 ? '1px solid #162032' : 'none',
                    fontSize: '13px',
                    lineHeight: 1.5,
                  }}
                >
                  <span style={{ color: 'var(--accent-teal)', userSelect: 'none', flexShrink: 0 }}>
                    [{String(idx + 1).padStart(2, '0')}]
                  </span>
                  <span style={{ color: 'var(--text-primary)' }}>{rec}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 4. Detected Anomalies List */}
        <div style={{ marginBottom: '24px' }}>
          <div className="meta-label" style={{ fontSize: '12px', color: 'var(--accent-teal)', marginBottom: '8px' }}>
            &gt; 04. TELEMETRY ANOMALIES IDENTIFIED [{anomalies.length}]
          </div>

          {anomalies.length === 0 ? (
            <div
              style={{
                backgroundColor: 'var(--bg-main)',
                border: '1px solid var(--border-color)',
                borderRadius: '2px',
                padding: '14px',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}
            >
              No specific log anomaly clusters flagged during inspection.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }} id="report-anomalies-list">
              <table className="terminal-table">
                <thead>
                  <tr>
                    <th style={{ width: '110px' }}>SEVERITY</th>
                    <th style={{ width: '180px' }}>ANOMALY TYPE</th>
                    <th style={{ width: '90px' }}>COUNT</th>
                    <th>SAMPLE / DETAIL</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.map((anom, idx) => {
                    const sampleText = extractAnomalySample(anom);
                    const anomalyType = anom?.type || anom?.name || anom?.results?.[0]?.type || 'unclassified';
                    const count = anom?.count ?? anom?.results?.[0]?.count ?? 1;
                    const sev = anom?.severity || anom?.results?.[0]?.severity || 'medium';

                    return (
                      <tr key={idx}>
                        <td>
                          <SeverityBadge severity={sev} />
                        </td>
                        <td>
                          <span style={{ color: 'var(--accent-teal)' }}>
                            {anomalyType}
                          </span>
                        </td>
                        <td>
                          <span style={{ color: 'var(--text-secondary)' }}>
                            {count}
                          </span>
                        </td>
                        <td>
                          <span style={{ color: '#94a3b8', fontSize: '12px', wordBreak: 'break-all' }}>
                            {sampleText}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 5. Retrieved Runbooks (if any) */}
        {runbooks.length > 0 && (
          <div>
            <div className="meta-label" style={{ fontSize: '12px', color: 'var(--accent-teal)', marginBottom: '8px' }}>
              &gt; 05. REFERENCED RUNBOOKS & SOPs [{runbooks.length}]
            </div>
            <div style={{ display: 'grid', gap: '8px' }}>
              {runbooks.map((rb, idx) => (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-main)',
                    border: '1px solid var(--border-color)',
                    padding: '10px 14px',
                    borderRadius: '2px',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: 'var(--accent-teal)', marginRight: '8px' }}>
                    [DOC-{idx + 1}]
                  </span>
                  <span style={{ color: 'var(--text-primary)' }}>
                    {rb.title || rb.name || rb.service || JSON.stringify(rb)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
