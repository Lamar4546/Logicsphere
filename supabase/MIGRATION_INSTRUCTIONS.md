Migration application and PostgREST refresh instructions

1) Apply the migration

- Using `psql` with a connection string (service role/admin):

```bash
psql "<CONNECTION_STRING>" -f supabase/migrations/001_add_org_columns.sql
```

- Or paste the contents of `supabase/migrations/001_add_org_columns.sql` into the Supabase SQL editor and run it.
 - To remove the FK from `app_users.id` -> `auth.users(id)`, run:

```bash
psql "<CONNECTION_STRING>" -f supabase/migrations/002_drop_app_users_fk.sql
```

Or paste `supabase/migrations/002_drop_app_users_fk.sql` into the Supabase SQL editor and run it.

2) Refresh PostgREST / schema cache

PostgREST (the Supabase REST layer) caches schema metadata. After changing the schema you should restart the PostgREST process so it rebuilds its cache.

- If running Supabase locally with Docker Compose:

```bash
# from repo root (where docker-compose.yaml is located for local supabase)
docker compose restart postgrest
# or restart the whole stack
docker compose restart
```

- If using the Supabase CLI local dev stack:

```bash
supabase stop
supabase start
```

- If you are on Supabase Cloud the dashboard typically picks up migrations automatically; if you still see PostgREST errors, try redeploying the project from the dashboard or opening a support ticket. In many cases the SQL editor run is sufficient and PostgREST refreshes automatically.

3) Verify

- From the backend machine, run a simple psql query to confirm columns exist:

```bash
psql "<CONNECTION_STRING>" -c "\d+ organizations"
```

- Or from Supabase SQL editor:

```sql
select column_name, data_type from information_schema.columns where table_name='organizations';
```

4) Retry register flow

- Restart your backend (if it was running during schema change):

```bash
cd backend
python run.py
```

- Then POST to `/api/auth/register` to confirm registration succeeds.

Notes

- Use a database user with sufficient privileges to alter the schema (service role or admin). Do not expose such credentials to the client.
- If your deployment uses additional caching layers (API gateways, reverse proxies), restart those as needed.
