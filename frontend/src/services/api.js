/**
 * SherLog Centralized API Service
 * Communicates with the FastAPI backend (/api/v1/...)
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const API_V1 = `${BASE_URL}/api/v1`;

async function request(endpoint, options = {}) {
  const url = `${API_V1}${endpoint}`;
  const config = {
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);

    // Parse JSON or text
    let data;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg =
        (typeof data === 'object' && (data?.detail || data?.message || data?.error)) ||
        (typeof data === 'string' && data) ||
        `HTTP ${response.status} ${response.statusText}`;
      const error = new Error(errorMsg);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  } catch (err) {
    if (err.status) throw err;
    // Network / connection error
    const netErr = new Error(`Cannot reach SherLog backend at ${BASE_URL}. Ensure backend is running.`);
    netErr.status = 0;
    throw netErr;
  }
}

// -------------------------------------------------------------
// Health Check
// -------------------------------------------------------------
export async function getHealth() {
  return request('/health');
}

// -------------------------------------------------------------
// Incidents API
// -------------------------------------------------------------
export async function getIncidents({ skip = 0, limit = 20, status = '', severity = '' } = {}) {
  const params = new URLSearchParams();
  params.append('skip', skip);
  params.append('limit', limit);
  if (status) params.append('status', status);
  if (severity) params.append('severity', severity);

  return request(`/incidents?${params.toString()}`);
}

export async function getIncident(incidentId) {
  return request(`/incidents/${incidentId}`);
}

export async function createIncident(payload) {
  return request('/incidents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function updateIncidentStatus(incidentId, status) {
  return request(`/incidents/${incidentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

// -------------------------------------------------------------
// Logs API
// -------------------------------------------------------------
export async function uploadIncidentLogs(incidentId, file) {
  const formData = new FormData();
  formData.append('file', file);

  return request(`/incidents/${incidentId}/logs`, {
    method: 'POST',
    // Do NOT set Content-Type header so browser sets multipart boundary automatically
    body: formData,
  });
}

export async function getIncidentLogs(incidentId) {
  return request(`/incidents/${incidentId}/logs`);
}

// -------------------------------------------------------------
// Investigations & Reports API
// -------------------------------------------------------------
export async function triggerInvestigation(incidentId) {
  return request(`/incidents/${incidentId}/investigate`, {
    method: 'POST',
  });
}

export async function getInvestigationStatus(incidentId) {
  return request(`/incidents/${incidentId}/investigation`);
}

export async function getIncidentReport(incidentId) {
  return request(`/incidents/${incidentId}/report`);
}
