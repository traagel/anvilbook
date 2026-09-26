# anvilbook central server: design

## Purpose

Let people check auction prices and crafting profits on a website, without being in game.
Desktop clients push what they scan; the site serves everyone, including people who never run
the app.

Intent, as agreed:

- Players opt in to sharing. Sharing prices and sharing a character's crafting are separate
  choices, both off by default.
- Accounts use a username and password, with no email.
- The site shows an item price browser **and** a crafting profit table.
- The server runs as a Docker image on k3s with Postgres. TLS, ingress, and the tunnel to
  Hetzner are handled outside this project.

## Non-goals

- Password reset, email, or any account recovery. A forgotten password means a lost account
  unless the operator resets the hash by hand. The sign-up form says so.
- Moderation tools, bans, reputation, or a web UI for administration.
- Realm-wide "market value" statistics across contributors. The first version shows the latest
  scan per realm and the history of scans.
- Uploading bags, gold, disenchant results, or anything else the desktop app records.

## Constraints

- One image, `ghcr.io/traagel/anvilbook-server`, built by the existing release workflow.
- Postgres is provided by the operator through `DATABASE_URL`.
- The app listens on `PORT` (default 8000) and terminates no TLS itself.
- The desktop client must keep working with no server configured, and its install must not grow.

## Package layout

The server lives in the same repository and shares the crafting code, so the site and the app
cannot drift apart.

```
src/anvilbook/            desktop app (unchanged)
src/anvilbook/server/     new: api.py, db.py, auth.py, schema.sql, static/
src/anvilbook/push.py     new: client side of the upload
deploy/                   new: Kubernetes YAML and Dockerfile
```

`pyproject.toml` gains an optional extra:

```toml
[project.optional-dependencies]
server = ["psycopg[binary]>=3.2"]
```

`uvx anvilbook` stays exactly as it is. The image installs `.[server]`.

## Data model

Plain SQL, applied at startup with `CREATE TABLE IF NOT EXISTS`, in the style of the local store.

```sql
users              (id, username UNIQUE, password_hash, created_at)
tokens             (token_hash PRIMARY KEY, user_id, created_at, last_used_at)
realms             (id, name UNIQUE)
scans              (id, user_id, realm_id, taken_at, uploaded_at, item_count)
prices             (scan_id, item_id, min_price, available, day_high, PRIMARY KEY (scan_id, item_id))
characters         (id, user_id, realm_id, name, published, updated_at, UNIQUE (user_id, realm_id, name))
character_skills   (character_id, profession, rank, max_rank, PRIMARY KEY (character_id, profession))
character_recipes  (character_id, item_id, name, min_made, max_made, difficulty, reagents JSONB,
                    PRIMARY KEY (character_id, item_id))
```

Sizes: a full scan is about 2000 rows. A busy realm might see 50 scans a day, which is 100k rows a
day, or roughly 36M rows a year. Postgres handles that, and old scans can be pruned later by date.

`latest_prices(realm_id)` is a view over the newest scan per realm, which every read endpoint uses.

## API

### Accounts

- `POST /api/register` `{username, password}` creates the account. Usernames are 3 to 32
  characters of letters, digits, underscore, or hyphen. Passwords are at least 10 characters.
  Returns a token.
- `POST /api/login` `{username, password}` returns a token.
- `POST /api/logout` deletes the presented token.
- `DELETE /api/account` removes the user, their tokens, characters, scans, and prices.

Tokens are 32 random bytes, hex encoded, sent as `Authorization: Bearer <token>`, stored only as
a SHA-256 hash. Passwords use `hashlib.scrypt` with `n=2**15, r=8, p=1`, a per-user 16-byte salt,
and a 32-byte key, stored as `scrypt$n$r$p$salt$key`.

### Push, from the client

- `POST /api/push/scan` `{realm, taken_at, prices: [{item_id, min_price, available, day_high}]}`
- `POST /api/push/character` `{realm, name, professions: {...}, recipes: {...}, published}`
- `DELETE /api/push/character/{realm}/{name}` removes it from the site.

Both need a token. Limits: 5 MB per request, 20 pushes per hour per account, at most 20000 price
rows per scan, prices between 1 copper and 10 million gold, and a `taken_at` no more than 2 days
old or in the future. Violations return 400 or 429 with a plain explanation.

A scan with the same account, realm, and `taken_at` as an existing one replaces it, so a client
that retries cannot create duplicates.

Released clients must keep working: the server accepts unknown extra fields and never requires a
field that an older client does not send. Breaking changes get a new path, not a changed one.

### Public reads, no account needed

- `GET /api/realms`
- `GET /api/items/search?q=&realm=`
- `GET /api/items/{item_id}?realm=` current price, quantity, and the scan it came from
- `GET /api/items/{item_id}/history?realm=` points for the chart
- `GET /api/crafts?realm=&character=` the profit table
- `GET /api/characters?realm=` published characters with their professions

Crafting profits reuse `craft.Calculator`, `items.load_items`, and `disenchant`, fed by the
latest prices for the realm. Without a `character`, the table uses the item database's recipes.
With one, it uses that character's recipes and skill levels, exactly as the desktop app does.

The item database is downloaded once at startup and cached in a volume, the same file the app uses.

## The website

One static page served by the same container, fed by the public endpoints above. Same style and
palette as the app, no build step:

- Realm picker and item search
- An item view: current lowest price, quantity, when it was scanned, and a uPlot price history
- A crafting profit table, with an optional character selector for published characters
- A short page explaining what anvilbook is, with links to the releases and the addon

## Client changes

- New **Share** tab: server address, sign in or register, and 2 switches.
  - "Send my price scans" pushes after each successful import.
  - Per character, "Publish what this character can craft".
- Both default to off. The tab states exactly what each switch sends, in plain words, before it is
  turned on, and offers "Delete my account and everything I sent".
- `push.py` holds the HTTP calls, retries once, and never blocks the import. Failures show in the
  status bar and never lose local data.
- Settings gain `server_url`, `server_token`, `push_prices`, and the per-character publish flags.
  The token is stored in the local database, not in the config file.

## Security

- The server only accepts what it needs, and validates every field.
- No IP addresses are stored; rate limiting counts per account in memory, which assumes a single
  replica. Running more replicas needs the counter moved into Postgres first.
- Uploads are attributed to their uploader, so a bad contributor can be removed with one delete.
- Requests without a valid token can only read.
- TLS is the operator's job, and the README says the client refuses plain `http://` except for
  `localhost`.

## Deployment

- `deploy/Dockerfile`: python:3.13-slim, `pip install .[server]`, non-root user, `EXPOSE 8000`.
- `deploy/k8s.yaml`: Deployment, Service, and a Secret holding `DATABASE_URL`, plus a PVC for the
  item database cache. No Ingress; the operator wires their own.
- `GET /healthz` returns 200 when the database answers.
- The release workflow builds and pushes the image on each tag.

## Testing

- Pure logic without a database: password hashing, token handling, payload validation, rate limits.
- Database tests against a real Postgres, using the service container in CI. Locally they skip
  unless `ANVILBOOK_TEST_DATABASE_URL` is set.
- Client push tests run against a fake server, so no network is needed.
- The existing 102 tests must keep passing untouched.

## Risks

- **Bad data.** Anyone can push nonsense within the sanity limits. Accepted for now: scans are
  attributed, and removal is one delete. Cross-contributor agreement can come later.
- **Forgotten passwords.** No recovery by design. Stated on the form.
- **Growth.** If the price table grows uncomfortable, prune scans older than a chosen date.
