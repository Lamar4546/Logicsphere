# LogiSphere v2 — Technical Implementation Overview

This document summarizes the main technical work present in the repository as of November 1, 2026. It is based on the current source code, frontend, and database migrations. It describes implemented code paths; an available API or UI does not by itself mean a production provider or external system has been configured.

## 1. Application architecture

LogiSphere is organized as a Vue single-page application, a Flask REST API, and a Supabase/PostgreSQL data store.

- **Frontend:** Vue 3, Vue Router, Pinia, Vite, and Lucide icons. The app includes Command Center, Operations, Tracking, and Settings views, shared components, responsive styling, loading placeholders, and API calls through a shared service. Vite proxies `/api` to the local Flask server during development.
- **Backend:** Flask app factory with CORS, environment-based configuration, Supabase client initialization, and blueprints grouped by feature. A health endpoint is available at `/api/health`.
- **Data:** Supabase Auth handles identity and PostgreSQL stores application and logistics records. SQL migrations evolve the schema and apply organization-scoped row-level security policies.
- **Deployment support:** Gunicorn is included for serving the Python app; Vite has a production build and preview setup, with Vercel routing configuration in the frontend.

## 2. Sign-in and organization accounts

The account flow includes registration, login, logout response, profile read/update, password recovery/reset, and account deletion. Registration creates a Supabase Auth user, an organization, and an organization-linked application profile. Login verifies credentials with Supabase Auth and issues a signed application JWT containing the user and organization context. Protected API routes use a shared decorator to read and validate that token.

The backend uses a Supabase service key for server-side database/Auth operations. The frontend stores the application session and sends it with API requests. Password recovery is delegated to Supabase; the reset endpoint submits the recovery token to Supabase Auth. Account deletion removes that user profile and identity while retaining shared organization operational data.

## 3. Shipment monitoring and AI-assisted workflow

The main risk workflow connects shipment intake and tracking to recommendation and controlled action:

1. Shipments can be created through the API and evaluated for delay.
2. The Transportation Agent compares current and original ETA and produces a structured observation.
3. The Risk Agent assigns a delay severity, explains it, and records a risk alert.
4. The Central AI Logistics Manager combines those results into a recommendation that distinguishes observed facts, predictions, and proposed actions.
5. The policy engine decides whether an action can proceed autonomously or needs approval. The execution engine carries out approved actions; recommendations and workflow state are persisted.
6. The Communication Agent drafts customer-facing updates. The operator can approve/reject recommendations and approve communication as part of the workflow.

Agent runs and material workflow changes are written to `agent_runs` and `audit_events`. The dashboard API aggregates at-risk shipments, open alerts, pending recommendations, and draft communications for the signed-in organization.

An AI client supports MiniMax-compatible chat/JSON requests and environment-variable aliases for provider, URL, and model configuration. Agent paths include deterministic fallback behavior when AI is not configured or a request fails. Policy thresholds and approval rules are exposed to the Operations UI. AI output assists reasoning; backend policy and execution code control transactional actions.

## 4. Operations workspace

The Operations Console and API cover core order and delivery work:

- Create orders and corresponding shipments, import orders from CSV, update order details, and cancel orders.
- Maintain inventory quantities and reorder points, and create return records.
- Create delivery tasks through operations-agent logic and review operations data in a consolidated overview.
- Capture proof of delivery with recipient details and optional signature/photo data.
- Record order-change events with actor and event details for an order history.
- Provide an operations assistant endpoint backed by the configured AI client with a deterministic fallback response.

The operations schema includes orders, delivery tasks, inventory items, delivery proofs, returns, and order events. Shipment/order links connect new and backfilled orders to shipment tracking.

## 5. Maps, routes, and tracking

The frontend uses Leaflet and OpenStreetMap for shipment maps. Route lookup/geocoding code can resolve origin/destination coordinates, request a route, and persist route geometry, distance, duration, and lookup status. The shipment API accepts tracking updates such as latitude, longitude, ETA, event description, altitude, heading, and transport mode. The Command Center refreshes tracking data periodically, and the Tracking view presents shipment status and map information.

Public customer tracking links are capability-style tokens: the raw token is returned to the authenticated operator when generated, while the database stores its hash. A public tracking endpoint uses the presented token to retrieve a limited shipment-tracking view.

Multimodal support records plane, ship, or truck mode and tracking-source/telemetry attributes. Fleet overview components include a Cesium globe view and map presentation for shipment locations. These screens depend on incoming shipment coordinates; they do not themselves provide GPS or carrier telemetry.

## 6. Fleet load planning

Fleet planning adds organization-owned vehicle records and shipment load assignments. A vehicle stores a reference, optional driver/dock information, weight capacity, compartment count, and status. Load assignment checks vehicle/shipment ownership and available capacity, assigns a slot, and updates vehicle status. The Operations Console exposes vehicle registration, selecting a planning vehicle, and adding/removing shipment loads.

## 7. Notifications and external integrations

Notification delivery supports SMS, WhatsApp, and email senders through provider configuration held in backend environment variables. Delivery attempts, recipient/channel/content, provider message ID, result, and errors are recorded in `notification_log`. The UI and API can list shipment notification history and send a notification; sandbox configuration is available for safe provider testing.

Integration APIs support organization-scoped connection records for carrier, ERP, and WMS endpoints; carrier assignment creation and dispatch; and inbound record sync. Credentials are referenced by an environment-variable key rather than stored in the browser or integration connection row. Integration attempts are logged in `integration_sync_log`; imported financial records are persisted with an external ID for deduplication.

These are integration frameworks/adapters: each organization still needs a compatible provider endpoint, credentials, and configuration for live external exchange.

## 8. Database and tenant isolation

The base schema and migrations define organizations, users, shipments, alerts, recommendations, communications, workflows, tasks, audit records, and agent runs. Later migrations add operations records, notifications, integration connections and logs, shipment/order relationships, route metadata, order event history, multimodal tracking fields, hashed public tracking tokens, and fleet planning tables.

Tables holding organization data enable PostgreSQL row-level security and policies based on the current organization context. The API also scopes its queries and mutations by the organization ID from the validated application JWT. Database migrations must be applied to the target Supabase project for the corresponding feature to work; some screens report when optional migration-backed features are not yet ready.

## 9. API surface

The Flask app registers these API groups:

- `/api/auth` — account, session, and profile operations.
- `/api/command-center` — dashboard summary.
- `/api/shipments` — shipment intake, list, route refresh, tracking updates, evaluation, and public-link generation.
- `/api/track` — public token-based tracking lookup.
- `/api/recommendations` — recommendation approval and rejection.
- `/api/workflows` — workflow status and communication approval/execution.
- `/api/operations` — overview, rules, orders, CSV import, inventory, returns, delivery proofs, assistant, and fleet planning.
- `/api/notifications` — send and view shipment notification records.
- `/api/integrations` — connections, carrier assignments, dispatch, and synchronization.

## 10. Technical boundaries and follow-up work

The repository is an evolving application, not evidence that all integrations are connected in a live environment. The README still describes the original shipment-delay thin slice and does not document much of the newer code. External carrier/ERP/WMS providers, production notification credentials, live telemetry sources, and database migration state need environment-specific setup. The exact behavior available depends on which migrations have been applied.

The repository includes sender and integration test modules plus an auth test file. This overview is a source review; it does not claim that the current test suite, production deployment, database migrations, or live provider connections were executed or verified as part of writing this document.

## Main technologies

| Area | Technologies |
| --- | --- |
| Frontend | Vue 3, Vue Router, Pinia, Vite, Leaflet, Cesium, Lucide Vue |
| Backend | Python, Flask, Flask-CORS, Supabase Python client, Requests, Gunicorn |
| Database and identity | Supabase Auth, PostgreSQL, SQL migrations, row-level security |
| AI integration | MiniMax-compatible chat/JSON client with deterministic fallback paths |
| Maps | OpenStreetMap tiles, Leaflet, Cesium globe visualization |
| Notifications | SMS, WhatsApp, and email provider adapters |
