# Running the anvilbook server

The server collects price scans that anvilbook clients push, and serves a public page where
anyone can look up prices and crafting profits. It is optional: the desktop app works with no
server at all.

## What it stores

- **Accounts**: a username and a scrypt password hash. No email, no password reset, no IP
  addresses.
- **Scans**: for each upload, the realm, the time of the scan, and one row per item with the
  lowest price, the listed count, and the day high.
- **Characters**, only when the player publishes one: the name, the professions with skill
  levels, and the recipes the character knows.

Nothing else the app records is uploaded: not gold, not bags, not disenchant results.

Every upload is attributed to the account that sent it, so one bad contributor is one delete.

## Configuration

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | Postgres connection string. Required. |
| `PORT` | Port to listen on. Default 8000. |
| `ANVILBOOK_DATA` | Directory for the cached item database. Default `/data`. |

The tables are created at startup with `CREATE TABLE IF NOT EXISTS`, so there is no migration
step. The item database is downloaded once, on the first crafting request, into `ANVILBOOK_DATA`.

## Deploying on Kubernetes

```bash
kubectl create secret generic anvilbook \
  --from-literal=database-url='postgresql://anvilbook:secret@postgres:5432/anvilbook'
kubectl apply -f deploy/k8s.yaml
```

That creates a Deployment, a Service on port 80, and a 1 GiB PersistentVolumeClaim for the item
database cache. Point your own Ingress at the `anvilbook` Service.

`GET /healthz` returns 200 when the database answers; the Deployment uses it for both probes.

### Ingress notes

- **TLS is required.** Passwords and tokens cross the wire, and the client refuses a plain
  `http://` address unless it is `localhost`.
- **Cap the request body at 5 MB.** The application refuses a larger upload, but only after it
  has been received, so the limit belongs at the Ingress as well. On ingress-nginx that is
  `nginx.ingress.kubernetes.io/proxy-body-size: 5m`.

## Running it without Kubernetes

```bash
docker run -p 8000:8000 -e DATABASE_URL=postgresql://... -v anvilbook-data:/data \
  ghcr.io/traagel/anvilbook-server:latest
```

The release workflow builds and pushes that image on every tag.

## Limits

- Each account may push 20 times an hour, at most 20000 price rows a scan, with prices between
  1 copper and 10000 gold, and a scan time no more than 2 days from now.
- A scan with the same account, realm and scan time as an earlier one replaces it, so a client
  that retries cannot double its history.
- **Rate limiting counts in memory, so it assumes a single replica.** Run more than one replica
  only after moving the counter into Postgres.

## Removing a contributor

```sql
DELETE FROM users WHERE username = 'thename';
```

Their tokens, scans, prices and characters go with them, through `ON DELETE CASCADE`.

## Pruning old scans

The price table grows by about 2000 rows a scan. To trim it:

```sql
DELETE FROM scans WHERE taken_at < now() - interval '90 days';
```

## Tests

The database tests skip unless `ANVILBOOK_TEST_DATABASE_URL` points at a Postgres you can write
to. CI provides one; locally:

```bash
docker run -d --name anvilbook-pg -e POSTGRES_PASSWORD=dev -p 5433:5432 postgres:17
ANVILBOOK_TEST_DATABASE_URL=postgresql://postgres:dev@localhost:5433/postgres \
  uv run --extra server pytest -q
```
