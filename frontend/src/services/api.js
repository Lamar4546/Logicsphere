const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

const AUTH_TOKEN_KEY = 'ls_token'

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token)
  }
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY)
}

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || ''
}

export function logout() {
  clearAuthToken()
  localStorage.removeItem('ls_user')
}

async function request(path, options = {}) {
  const token = getAuthToken()

  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  console.log(`[API] ${options.method || 'GET'} ${path}`)
  console.log('[API] Token present:', !!token)

  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  })

  const body = await response.json().catch(() => ({}))

  if (!response.ok) {
    console.error('[API ERROR]', response.status, body)

    if (response.status === 401) {
      clearAuthToken()
      localStorage.removeItem('ls_user')
    }

    const error = new Error(
      body.error ||
      body.message ||
      `Request failed: ${response.status}`
    )
    error.status = response.status
    throw error
  }

  return body
}


/* =========================
   AUTH
========================= */

export async function register(payload) {
  const data = await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  const token = data.token || data.access_token

  if (token) {
    setAuthToken(token)
  }
  if (data.user) localStorage.setItem('ls_user', JSON.stringify(data.user))

  return data
}


export async function login(payload) {
  const data = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  const token = data.token || data.access_token

  if (token) {
    setAuthToken(token)
  }
  if (data.user) localStorage.setItem('ls_user', JSON.stringify(data.user))

  return data
}

export async function deleteAccount(confirmation) {
  return request('/auth/account', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation }),
  })
}

export async function updateProfile(payload) {
  return request('/auth/profile', { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function getProfile() { return request('/auth/profile') }
export async function requestPasswordReset(email) {
  return request('/auth/password/forgot', { method: 'POST', body: JSON.stringify({ email }) })
}
export async function resetPassword(payload) {
  return request('/auth/password/reset', { method: 'POST', body: JSON.stringify(payload) })
}


/* =========================
   COMMAND CENTER
========================= */

export async function getCommandCenterSummary() {
  return request('/command-center/summary')
}


/* =========================
   SHIPMENTS
========================= */

export async function listShipments() {
  return request('/shipments')
}


export async function createShipment(payload) {
  return request('/shipments', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}


export async function evaluateShipment(shipmentId) {
  return request(`/shipments/${shipmentId}/evaluate`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
export async function refreshShipmentRoute(shipmentId) {
  return request(`/shipments/${shipmentId}/route/refresh`, { method: 'POST', body: JSON.stringify({}) })
}


/* =========================
   RECOMMENDATIONS
========================= */

export async function approveRecommendation(
  recommendationId,
  notes = ''
) {
  return request(
    `/recommendations/${recommendationId}/approve`,
    {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }
  )
}


export async function rejectRecommendation(
  recommendationId,
  notes = ''
) {
  return request(
    `/recommendations/${recommendationId}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }
  )
}


/* =========================
   WORKFLOWS
========================= */

export async function approveCommunicationAndExecute(
  workflowId,
  communicationId
) {
  return request(
    `/workflows/${workflowId}/approve-communication`,
    {
      method: 'POST',
      body: JSON.stringify({
        communication_id: communicationId,
      }),
    }
  )
}
export async function importOrdersCsv(file) {
  const token = getAuthToken()
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE}/operations/orders/import`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })

  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(body.error || `Import failed: ${response.status}`)
    error.status = response.status
    throw error
  }
  return body
}

/* =========================
   OPERATIONS CONTROL PLANE
========================= */
export async function getOperationsOverview() { return request('/operations/overview') }
export async function createOrder(payload) { return request('/operations/orders', { method: 'POST', body: JSON.stringify(payload) }) }
export async function upsertInventory(payload) { return request('/operations/inventory', { method: 'POST', body: JSON.stringify(payload) }) }
export async function createReturn(payload) { return request('/operations/returns', { method: 'POST', body: JSON.stringify(payload) }) }

export async function listShipmentNotifications(shipmentId) { return request(`/notifications/shipment/${shipmentId}`) }
export async function sendNotification(payload) { return request('/notifications/send', { method: 'POST', body: JSON.stringify(payload) }) }
export async function createCarrierAssignment(payload) { return request('/integrations/carrier-assignments', { method: 'POST', body: JSON.stringify(payload) }) }
export async function dispatchCarrierAssignment(id) { return request(`/integrations/carrier-assignments/${id}/dispatch`, { method: 'POST', body: JSON.stringify({ confirm: true }) }) }
export async function syncIntegrationRecords(payload) { return request('/integrations/sync', { method: 'POST', body: JSON.stringify(payload) }) }
export async function listIntegrationConnections() { return request('/integrations/connections') }
export async function saveIntegrationConnection(payload) { return request('/integrations/connections', { method: 'POST', body: JSON.stringify(payload) }) }


/* =========================
   API OBJECT
========================= */

export const api = {
  register,
  login,
  deleteAccount,
  updateProfile,
  getProfile,
  requestPasswordReset,
  resetPassword,
  logout,

  getCommandCenterSummary,

  listShipments,
  createShipment,
  evaluateShipment,
  refreshShipmentRoute,

  approveRecommendation,
  rejectRecommendation,

  approveCommunicationAndExecute,
  getOperationsOverview,
  createOrder,
  importOrdersCsv,
  upsertInventory,
  createReturn,
  listShipmentNotifications,
  sendNotification,
  createCarrierAssignment,
  dispatchCarrierAssignment,
  syncIntegrationRecords,
  listIntegrationConnections,
  saveIntegrationConnection,
}
