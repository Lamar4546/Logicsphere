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
6. A human reviews and **approves or rejects** the recommendation
   (SRS §14.1 human-in-the-loop — nothing executes without this step).
7. On approval, the **Communication Agent** drafts a customer update.
8. A human approves the draft, which **executes the workflow** and writes
   an audit record (SRS §13.1 NFR-006).

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

AI agents produce **observations, predictions, and recommendations** —
never direct actions on money, inventory, or commitments. Every
recommendation requires human approval before the Communication Agent's
draft can be sent and the workflow marked complete. This mirrors the
project's existing rule that deterministic backend logic — not the AI —
owns anything transactional.

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
