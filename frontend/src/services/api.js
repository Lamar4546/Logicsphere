const BASE = '/api'

// Demo scope: org/user IDs are hardcoded until org auth/onboarding (SRS §8.1)
// is built in a later slice. Swap for real auth session values then.
export const DEMO_ORG_ID = import.meta.env.VITE_DEMO_ORG_ID || ''
export const DEMO_USER_ID = import.meta.env.VITE_DEMO_USER_ID || ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  getCommandCenterSummary(orgId = DEMO_ORG_ID) {
    return request(`/command-center/summary?organization_id=${orgId}`)
  },
  listShipments(orgId = DEMO_ORG_ID) {
    return request(`/shipments?organization_id=${orgId}`)
  },
  createShipment(payload) {
    return request('/shipments', {
      method: 'POST',
      body: JSON.stringify({ organization_id: DEMO_ORG_ID, ...payload }),
    })
  },
  evaluateShipment(shipmentId, orgId = DEMO_ORG_ID) {
    return request(`/shipments/${shipmentId}/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId }),
    })
  },
  approveRecommendation(recommendationId, orgId = DEMO_ORG_ID, reviewedBy = DEMO_USER_ID, notes = '') {
    return request(`/recommendations/${recommendationId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, reviewed_by: reviewedBy, notes }),
    })
  },
  rejectRecommendation(recommendationId, orgId = DEMO_ORG_ID, reviewedBy = DEMO_USER_ID, notes = '') {
    return request(`/recommendations/${recommendationId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, reviewed_by: reviewedBy, notes }),
    })
  },
  approveCommunicationAndExecute(workflowId, communicationId, orgId = DEMO_ORG_ID, approvedBy = DEMO_USER_ID) {
    return request(`/workflows/${workflowId}/approve-communication`, {
      method: 'POST',
      body: JSON.stringify({
        organization_id: orgId,
        communication_id: communicationId,
        approved_by: approvedBy,
      }),
    })
  },
}
