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

Run `supabase/migrations/009_backfill_order_shipments.sql` once after 008 to
create and link shipments for orders that existed before the automation.

Before enabling route maps, customer tracking links, or parcel tracking, apply
the applicable shipment migrations after the base schema: 010 (route fields),
012 (tracking telemetry), 013 (public link hashes), 015 (parcel provider
fields), and 016 (live provider identifiers). These migrations alter the existing `shipments` table; running them
before `supabase/schema.sql` creates that table will fail with “relation
shipments does not exist.”

Run `supabase/migrations/007_carrier_and_erp_wms_integrations.sql` to enable
carrier assignments plus inbound WMS inventory and ERP financial-record sync.
Configure each external connection in `integration_connections`; keep its
secret only in the server environment using the row's `auth_env_key` value.

Run `supabase/migrations/015_package_tracking.sql` to add parcel tracking IDs,
carrier status/checkpoint history, and separate carrier/AI delivery estimates.

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

Add `GROQ_API_KEY` (and optionally `GROQ_MODEL`) to `backend/.env`,
start the backend, then run:

```bash
cd backend
python demo_agent_workflow.py
```

The demo creates an 8-hour delay that is resolved autonomously and an
80-hour critical delay that appears in the Command Center's **Exceptions**
tab for human approval. Its printed `ai_provider` should be `groq`; if
Groq is unavailable it will be `deterministic_fallback` and the logistics
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

## Tracking simulation

The root-level simulate_tracking.py script sends simulated truck/ship
coordinates to the authenticated shipment tracking API. Apply
supabase/migrations/012_multimodal_tracking_telemetry.sql before any run because
the simulator sends transport_mode and tracking_source. If using --create-demo,
also apply supabase/migrations/010_shipment_route_lookup.sql for the route
fields used when it creates a shipment. Start the backend and frontend, then
run from the repository root:

    python simulate_tracking.py --mode both --create-demo --speed 3600 --delay-at 0.5 --evaluate-on-delay

The script prompts for a LogiSphere login unless LOGISPHERE_TOKEN is set.
--create-demo creates new demo shipments in the signed-in organization. With
existing shipments, omit --create-demo and set TRUCK_SHIPMENT_ID and/or
SEA_SHIPMENT_ID to shipment UUIDs visible to that account. LOGISPHERE_API
can override the default http://localhost:5000.
Run it in a Python environment with the backend requirements installed
(requests is required).

The example injects a three-hour ETA delay halfway through each route and
evaluates the shipment, which should cross the current two-hour low-risk
threshold. --speed 3600 keeps the sea route short enough for a demo. The
simulator updates coordinates, ETA, transport mode, source, and event text. It
does not change shipment status to delivered; the final waypoint is recorded
as a tracking event.

### Live phone tracking with Traccar

`traccar_bridge.py` connects a real phone running Traccar Client to one
LogiSphere shipment. Traccar owns device intake; the bridge polls its latest
position and forwards changed fixes through the existing authenticated
shipment tracking API. Keep the bridge running while viewing the shipment in
the Command Center map (which refreshes every 15 seconds).

For a quick local test, run Traccar where the phone can reach it. Docker's
default web interface is on 8082; Traccar Client's default OsmAnd listener is
TCP port 5055:

```bash
docker run --name traccar --detach --restart unless-stopped \
  --publish 8082:8082 --publish 5055:5055 traccar/traccar:latest
```

Open `http://localhost:8082`, create/sign into a Traccar account, and add a
device. Install **Traccar Client** on the phone and set its Device identifier
to the device's unique identifier in Traccar. Set Server URL to
`http://<computer-LAN-IP>:5055` (not `localhost`, which points back to the
phone), grant location permission, and enable background location. For a
phone outside the same Wi-Fi, use a publicly reachable host with TCP 5055
forwarded to Traccar. Choose a short distance/interval for the demo and expect
battery use to rise with more frequent GPS updates.

Run the bridge from the repository root with the environment values below.
Use `--create-demo` to create a new in-transit Kingston-to-Montego Bay
shipment automatically, or set `LOGISPHERE_SHIPMENT_ID` to update an existing
shipment:

```text
TRACCAR_URL=http://localhost:8082
TRACCAR_DEVICE_UNIQUE_ID=<identifier-from-phone-app>
LOGISPHERE_API=http://localhost:5000
# Set LOGISPHERE_SHIPMENT_ID only when not using --create-demo.
TRACCAR_POLL_SECONDS=5
```

For the phone test, run `python traccar_bridge.py --create-demo --mode land`.
The `--mode` option accepts `land`, `sea`, or `air` and writes the matching
road/ocean/air mode plus truck/ship/plane transport mode to the shipment. For
an existing shipment, set `LOGISPHERE_SHIPMENT_ID` and run for example
`python traccar_bridge.py --mode land`. Sea and air modes suppress the road
route overlay; Traccar still reports the tracked device's coordinates, heading,
and altitude. A Traccar device must physically travel with the load or vehicle
and have GPS/network access. The phone is a proxy for a land shipment test;
Traccar alone does not provide a ship's AIS position or an aircraft's ADS-B
position, and a normal phone may not report positions while offshore or
in-flight.

The bridge prompts for both account logins unless you supply usernames/passwords
or `TRACCAR_TOKEN` and `LOGISPHERE_TOKEN` in environment variables. Credentials
are used by this local bridge and are never sent to the browser. Add `--once` to
send one position for a connection check. The shipment marker should move on
the Command Center after the phone reports a new GPS fix. The update is
recorded with `tracking_source=traccar`.

For a first test, put the phone and Traccar host on the same trusted Wi-Fi.
For remote use, deploy Traccar behind HTTPS for its web/API access and expose
only the device protocol port needed by the phone. Use a dedicated Traccar
account with access to only the test device. Traccar recommends WebSocket for
live consumers; this bridge polls the latest position to keep the one-shipment
phone test easy to run and inspect.

### Live land, sea, and air sources

Apply migration 016 after 015. In the shipment map's **Configure live location
source** panel, choose a mode and enter its live identifier: a Traccar device
unique ID for land, a 9-digit vessel MMSI for sea, or a 6-character ICAO24 hex
address for air. This identifier links the shipment (and its parcel tracking
number) to the moving carrier asset. A parcel tracking number alone does not
identify which truck, vessel, or aircraft currently carries it.

Set `AISSTREAM_API_KEY` for sea and `OPENSKY_CLIENT_ID` plus
`OPENSKY_CLIENT_SECRET` for air in `backend/.env`. OpenSky is suitable for
testing/evaluating the API; its terms require commercial entities and continued
operational users to obtain a license. Then run the live position bridge with
the shipment UUID:

```bash
python multimodal_tracking_bridge.py --shipment-id <shipment-uuid>
```

The bridge reads the selected mode and identifier from that shipment, receives
vessel positions from AISStream, aircraft ADS-B positions from OpenSky, or GPS
positions from Traccar, and forwards all three into the existing shipment
telemetry endpoint. It reconnects to AISStream if its WebSocket drops. The God’s
Eye map uses the resulting coordinates and mode-specific markers. Run one
bridge process per shipment during this test deployment. Install bridge
dependencies with `python -m pip install -r backend/requirements.txt` first.

These feeds provide asset positions, not package delivery scans. Keep 17TRACK
or AfterShip enabled for parcel events and estimated delivery dates; those
updates combine with the live asset marker on the customer tracking page.
AISStream is an event-driven WebSocket feed with no uptime guarantee, and
OpenSky coverage varies by receiver coverage. OpenSky does not provide current
commercial flight schedules or delay/cancellation data. Land, sea, and air
source IDs must be associated with the right shipment by an operator or by a
future carrier integration; carrier APIs do not reliably expose these IDs from
a package tracking number alone. AISStream currently permits up to three
connections per account; run a shared stream worker before scaling beyond a
few simultaneous vessel tests.

### Track online-store packages by tracking number

The Shipments view creates a LogiSphere shipment from a carrier tracking
number. By default, it uses 17TRACK and auto-detects the carrier; an optional
numeric 17TRACK carrier code can be entered when auto-detection is ambiguous.
Set `PACKAGE_TRACKING_PROVIDER=17track` and `SEVENTEEN_TRACK_API_KEY` in
`backend/.env`. New 17TRACK API accounts currently receive a one-time test
allocation of 200 tracking numbers. The key stays on the backend. For
AfterShip, set `PACKAGE_TRACKING_PROVIDER=aftership` and `AFTERSHIP_API_KEY`.
Apply migration 015 before using the form.

The internal shipment detail and customer-facing `/track/<token>` page show
carrier status, arrival estimate, map location, and scan history. A staff user
can create a public link with “Share tracking link”. The public endpoint only
returns shipment status and filtered scan details; it omits recipient contact
details and full addresses. It polls periodically, while a webhook can update
the shipment as soon as a status changes.

When AfterShip supplies its AI estimated delivery date, LogiSphere stores it
separately from the carrier ETA and shows a countdown. Later ETA revisions can
be assessed with the existing Evaluate action, which runs the shipment delay
and risk agents. If the carrier/provider supplies no estimate, LogiSphere
does not invent a precise arrival time from the tracking number alone.

For 17TRACK push updates, configure its webhook URL as
`https://<your-backend-host>/api/webhooks/17track` in the 17TRACK API dashboard.
The backend validates its SHA-256 signature. AfterShip can instead post to
`/api/webhooks/aftership` with `AFTERSHIP_WEBHOOK_SECRET` configured. Without a
webhook, operators can use Refresh carrier status and the customer page polls
for updates. Carrier checkpoint coordinates are used when available; otherwise
the scan location is geocoded as an approximate map pin. Any line to a known
destination is a straight-line visualization, not a carrier route or live GPS.

This tracks the carrier shipment represented by the number. Amazon, Temu, and
SHEIN orders can use it when their tracking number is supported by the tracking
provider; marketplace-private numbers and unsupported courier services may
need a carrier slug or may not return events. LogiSphere does not sign into
those shopping accounts or retrieve order numbers itself.

For Caribbean shipping context, the DeepWorks feed catalog can complement
carrier events: `ferries-svg` and `ferries-caribbean` provide curated ferry
schedules/fares; `nhc-storms` and `nws-weather` can flag weather disruption;
`aviation-metar` gives airport conditions (not flight delays); and `eccb-fx`
provides daily XCD exchange rates for landed-cost and financial displays.
`worldbank-port-teu` is a sparse historical port-throughput indicator, not live
container tracking. These feeds do not contain parcel scan events or tracking
numbers. Store-feed snapshots require a DeepWorks API key; historical access
and webhooks require a paid feed plan. Feed values should be shown with source
and fetched time, and weather/throughput should be treated as context rather
than a per-parcel ETA.
