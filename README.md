# LogiSphere AI v2.0 — Thin Slice

New codebase, built against the **Improved SRS v2.0** (Virtual Logistics
Assistant Manager). This is not the buildathon MVP — it's a from-scratch
architecture, starting with one vertical slice built end-to-end so it's
demoable Friday and extensible toward the full SRS afterward.

## What's built

**Command Center** (SRS §5.1) — a dashboard with Today counts, an at-risk
shipment list, pending AI recommendations, and pending communications.

**Shipment Delay Workflow, end-to-end** (SRS §10.2) — the one workflow
fully wired from data entry to executed action:

1. Shipment enters the platform (manual entry stands in for a TMS sync).
2. **Transportation Agent** observes delay vs. original ETA.
3. **Risk Agent** classifies severity and opens a risk alert.
4. **Central AI Logistics Manager** prioritizes and generates a
   recommendation — with facts, predictions, and recommended action kept
   separate (SRS §14.2 explainability).
5. Shipment shows as "at risk" on the Command Center.
6. The Central Manager applies policy: routine operational work completes
   automatically; **critical risks and monetary commitments** pause for human
   approval.
7. The **Communication Agent** drafts routine customer updates; the
   notification service delivers approved auto-send drafts through the chosen
   provider and records every outcome.
   Once a human approves an exception, the remaining workflow completes and
   is recorded in the audit trail (SRS §13.1 NFR-006).

Every agent run is logged to `agent_runs` (success or failure) and every
material step to `audit_events` — so the system is observable and
auditable from the first slice, not bolted on later.

## Architecture

```
backend/
  app/
    agents/
      base.py                 # shared contract: typed output (observation/
                               #   prediction/recommendation/action), logging,
                               #   org-scoped access — SRS §7.1
      transportation_agent.py # observes shipment delay
      risk_agent.py           # classifies risk, opens risk_alerts
      communication_agent.py  # drafts customer/supplier messages
      central_manager.py      # orchestrator — SRS §6.2
    blueprints/                # Flask REST endpoints
    services/
      supabase_client.py
      workflow_service.py     # approval -> execution -> audit
frontend/
  src/
    views/CommandCenter.vue
    components/               # TodayStrip, ShipmentIntakeForm, ShipmentList,
                               #   RecommendationCard, CommunicationCard
    services/api.js
supabase/
  schema.sql                  # entities for this slice + RLS tenant isolation
```

### Design principle carried over from the buildathon build

AI agents can autonomously complete routine, non-financial logistics work
through the controlled execution layer. Critical incidents and anything that
creates a monetary or commercial commitment require human approval. The AI
does not directly execute those sensitive actions; deterministic backend
logic owns the approved transactional boundary.

## Running it

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SUPABASE_URL and SUPABASE_SERVICE_KEY
python run.py
```

### Database
Run `supabase/schema.sql` against a Supabase project (SQL editor or CLI).
You'll need at least one row in `organizations` and one in `app_users` to
demo against — insert manually for now; onboarding (§10.1) is a later slice.

For the Operations workspace, also run
`supabase/migrations/005_operations_control_plane.sql`. It creates the
organization-scoped orders, dispatch tasks, inventory, proof-of-delivery, and
returns records used by the operations agents.

Then run `supabase/migrations/006_live_tracking_notifications.sql`. It adds
shipment contact preferences and the `notification_log` audit trail required
for delivery status and the live-notification workflow.

Run `supabase/migrations/007_carrier_and_erp_wms_integrations.sql` to enable
carrier delivery assignments, WMS inventory imports, ERP financial-record
imports, and integration audit logs. Configure the provider URL in the
integration connections API and keep its API token in a matching backend
environment variable (for example `CARRIER_API_TOKEN`), never in the browser.

Run `supabase/migrations/008_order_shipment_link.sql` to link each in-app
order to the shipment created by dispatch. After this, creating or importing
an order makes it appear in the Control Tower immediately.

Run `supabase/migrations/007_carrier_and_erp_wms_integrations.sql` to enable
carrier assignments plus inbound WMS inventory and ERP financial-record sync.
Configure each external connection in `integration_connections`; keep its
secret only in the server environment using the row's `auth_env_key` value.

### Frontend
```bash
cd frontend
npm install
# create .env with:
#   VITE_DEMO_ORG_ID=<your org uuid>
#   VITE_DEMO_USER_ID=<your user uuid>
npm run dev
```
Vite proxies `/api` to `localhost:5000`.

### Live map and notification sandbox

The tracking map uses Leaflet with OpenStreetMap tiles and does not need a
Google Maps key. A carrier, driver, or GPS adapter can update the displayed
marker with `POST /api/shipments/<shipment_id>/tracking` using `latitude`,
`longitude`, and optionally `eta_current` and `last_event_description`. The
Command Center polls every 15 seconds and updates the selected shipment's
marker.

For safe testing, keep `SENDGRID_SANDBOX_MODE=true`. Add Twilio sandbox/test
credentials and a SendGrid sandbox sender only to `backend/.env`; never put
these credentials in the frontend. Every provider attempt is recorded in
`notification_log`, including missing credentials and provider failures.

Run sender-only tests without the agents or a database:

```bash
cd backend
python -m unittest tests.test_sender
```

### Observe the agent workflow

Add `MINIMAX_API_KEY` (and optionally `MINIMAX_MODEL`) to `backend/.env`,
start the backend, then run:

```bash
cd backend
python demo_agent_workflow.py
```

The demo creates an 8-hour delay that is resolved autonomously and an
80-hour critical delay that appears in the Command Center's **Exceptions**
tab for human approval. Its printed `ai_provider` should be `minimax`; if
MiniMax is unavailable it will be `deterministic_fallback` and the logistics
workflow still completes safely.

## What's deliberately NOT in this slice

Everything else in the SRS: inventory/procurement/supplier/warehouse
intelligence, document OCR, conversational assistant, customer onboarding
UI, real auth, real carrier/ERP integrations, workflow automation beyond
this one type. Section 21 of the SRS ("Open Product Decisions") still
applies — none of those are resolved here. This slice exists to prove the
agent → recommendation → human-approval → execution pattern works, in a
shape a logistics-industry contact can actually look at Friday.

## Next slices (suggested order)

1. Org/user auth + onboarding (§10.1) — needed before this can run against
   anything but a manually-seeded org.
2. Inventory risk workflow (§10.3) — reuses the same Central Manager /
   agent / recommendation / approval pattern.
3. Document workflow (§10.4) — introduces OCR and a new agent type.
4. Real TMS/carrier integration to replace the manual shipment intake form.
