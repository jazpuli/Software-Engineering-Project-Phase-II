/**
 * Trustworthy Model Registry - Frontend JavaScript
 */

// API base URL
const API_BASE = '';

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Format date for display
 */
function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/**
 * Get score class based on value
 */
function getScoreClass(score) {
  if (score >= 0.7) return 'score-high';
  if (score >= 0.4) return 'score-medium';
  return 'score-low';
}

/**
 * Format score for display
 */
function formatScore(score) {
  if (score === undefined || score === null) return 'N/A';
  if (score === -1) return 'N/A';
  return (score * 100).toFixed(0) + '%';
}

/**
 * Get status class based on status string
 */
function getStatusClass(status) {
  switch (status.toLowerCase()) {
    case 'healthy': return 'status-healthy';
    case 'degraded': return 'status-degraded';
    case 'unhealthy': return 'status-unhealthy';
    default: return '';
  }
}

/**
 * API Helper Functions
 */
const api = {
  async get(endpoint) {
    const response = await fetch(`${API_BASE}${endpoint}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  async post(endpoint, data) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  async delete(endpoint) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'DELETE'
    });
    if (!response.ok && response.status !== 204) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return true;
  }
};

/**
 * Artifact API
 */
const artifacts = {
  async list() {
    return api.get('/artifacts');
  },

  async get(type, id) {
    return api.get(`/artifacts/${type}/${id}`);
  },

  async create(type, data) {
    return api.post(`/artifacts/${type}`, data);
  },

  async delete(type, id) {
    return api.delete(`/artifacts/${type}/${id}`);
  },

  async search(query) {
    return api.get(`/artifacts/search?query=${encodeURIComponent(query)}`);
  },

  async rate(type, id) {
    return api.post(`/artifacts/${type}/${id}/rating`, {});
  },

  async getRating(type, id) {
    return api.get(`/artifacts/${type}/${id}/rating`);
  },

  async getLineage(type, id) {
    return api.get(`/artifacts/${type}/${id}/lineage`);
  },

  async getCost(type, id) {
    return api.get(`/artifacts/${type}/${id}/cost`);
  },

  async download(type, id) {
    return api.get(`/artifacts/${type}/${id}/download?part=full`);
  }
};

/**
 * Ingest API
 */
const ingest = {
  async huggingface(url, type = 'model') {
    return api.post('/ingest', { url, artifact_type: type });
  }
};

/**
 * Health API
 */
const health = {
  async get() {
    return api.get('/health');
  },

  async components() {
    return api.get('/health/components');
  }
};

/**
 * Reset API
 */
const system = {
  async reset() {
    return api.post('/reset', {});
  }
};

/**
 * Show notification message
 */
function showNotification(message, type = 'success') {
  // Remove existing notifications
  const existing = document.querySelector('.notification');
  if (existing) existing.remove();

  const notification = document.createElement('div');
  notification.className = `alert alert-${type} notification fade-in`;
  notification.role = 'alert';
  notification.textContent = message;
  notification.style.position = 'fixed';
  notification.style.top = '20px';
  notification.style.right = '20px';
  notification.style.zIndex = '1000';
  notification.style.maxWidth = '400px';

  document.body.appendChild(notification);

  setTimeout(() => {
    notification.remove();
  }, 5000);
}

/**
 * Confirm action dialog
 */
function confirmAction(message) {
  return confirm(message);
}

// Export for use in pages
window.api = api;
window.artifacts = artifacts;
window.ingest = ingest;
window.health = health;
window.system = system;
window.escapeHtml = escapeHtml;
window.formatDate = formatDate;
window.formatScore = formatScore;
window.getScoreClass = getScoreClass;
window.getStatusClass = getStatusClass;
window.showNotification = showNotification;
window.confirmAction = confirmAction;

