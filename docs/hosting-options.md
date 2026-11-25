# Hosting the Schnaps site on a public provider

Research only: nothing was bought, no account was made, no code was
changed. Prices were read from the providers' pages on **2026-11-25**
(sources at the end). Prices change often, so check the page again before
you order.

**Short answer:** a small x86 VPS with 2 vCPU and 4 GB RAM, Docker, Caddy
for HTTPS, and a cheap domain. The best fit is **netcup VPS 500 G12.5 in
Vienna**, about **€10–11 a month** with VAT, or a bit more on a monthly
term. Add **€0.50 a month** for a `.eu` domain. If you'd rather have an
hourly-billed cloud with an API and snapshots, use **Hetzner CPX22 in
Helsinki** for about **€21 a month** with VAT. Before the site goes
public, the watch port (8001) must be closed or behind a password, and
the login and register endpoints need rate limiting (section 5).

## 1. What has to run

From the code (`server/schnaps_web/app.py`, `config.py`, `scripts/env.sh`):

| Need | Detail |
|---|---|
| Process | One Python process, `python -m schnaps_web.app`: uvicorn serves the game on **8000** and the all-cards watch app on **8001**. Both share one in-memory lobby. |
| Python | **3.14** (the open_spiel venv), with jax/jaxlib **0.12.0.1** (CPU), flax 0.12.10, dm-haiku, optax, orbax-checkpoint, chex, tfp-nightly, numpy 2.5, fastapi, uvicorn[standard]. Pinned list: `open_spiel/gpu_pod/requirements.txt`. |
| pyspiel | `pyspiel.so`, built with CMake and Ninja from the `schnaps` branch of `github.com/marco-o/open_spiel`. The Ninja target is `python/pyspiel.so`. Only the Python build is on; ACPC, Hanabi, libtorch and the rest are off. **Note:** `open_spiel/games/schnaps/schnaps.{cc,h}` have uncommitted changes, so a clone from GitHub would build a different engine from the laptop's. Push them first, or build from the local tree. |
| open_spiel Python | `open_spiel.python.scale.*` and `open_spiel.python.jax.games.schnaps`, imported from the repo root (`PYTHONPATH=$OPEN_SPIEL:$OPEN_SPIEL/build/python`). |
| Models | `models/basic_player` (4.7 MB), `large_player` (21 MB), `mixed_player` (18 MB). Git ignores them, so a build from GitHub won't have them. Copy them into the image, or onto the server's disk. |
| Data | `data/db/schnaps.db`, one SQLite file (before 2026-11-25: three JSON files, 113 KB). One process owns it; it needs a local disk with working file locks. `SCHNAPS_WEB_DB_DIR` moves it. |
| Client | `client/dist` (720 KB), built with Node 22 and Vite. FastAPI serves it. The WebSocket URL follows the page's scheme (`wss://` on HTTPS, in `client/src/net/use_table.ts`), so HTTPS needs no client change. The client pings every 25 s and reconnects after 2 s. |
| Resources | About **1.3 GB RAM** measured, plus a burst while the three players load and compile (about 30 s each). Bot moves use CPU: JAX inference runs in `asyncio.to_thread`, and Napoli takes 0.3–6 s of CPU per decision. |
| Settings | Environment variables `SCHNAPS_WEB_<FIELD>`: `HOST`, `PORT`, `WATCH_PORT` (0 turns it off), `MAX_TABLES` (default 50), `SEARCH_SAMPLES` (0 drops Napoli), `BOT_DELAY`, `DB_DIR`, … |

So the server needs **≥2 GB RAM (4 GB is comfortable), 2 vCPU, a
persistent disk** and WebSockets. It also needs **exactly one
instance**: tables live in memory, and the database files allow only
one writer. That last point rules out autoscaling, scale-to-zero and
more than one replica on the container platforms.

## 2. Providers and plans

Prices are per month. "ex VAT" means VAT is added on top: an Austrian
private customer pays **20%**, an Italian one **22%**.

### 2a. VPS (a Linux machine you run Docker on)

WebSockets and persistent disk work on every VPS: it is your own machine,
and its disk persists.

| Provider | Plan that fits | vCPU / RAM / disk | Price | EU locations | Notes |
|---|---|---|---|---|---|
| **netcup** | **VPS 500 G12.5** | 2 vCore x86 / 4 GB / 64 GB SSD | **€9.50 incl. 19% DE VAT** on a 1-month term, **€8.26** on 12 months (about €7.98 / €6.94 net); 24-month term €7.03 incl. VAT | **Vienna**, Nuremberg, Amsterdam (+€1.04 for picking one; "no preference Europe" is free) | IPv4 included; traffic flat, throttled to 200 Mbit/s above 2 TB/day average; snapshots included. The only provider here with a data centre in Austria. |
| netcup | VPS 1000 G12.5 | 4 vCore / 8 GB / 128 GB | €16.68 (1 mo) / €14.50 (12 mo) incl. 19% VAT | same | Headroom for many bot tables. |
| **OVHcloud** | **VPS-1** | 2 vCore / 4 GB / 40 GB NVMe | **"from €3.81 ex VAT"** | France, Germany, Poland, UK and others (the page didn't list them) | Cheapest found. Unlimited traffic at 500 Mbit/s; daily backup of the last 24 h included. "From" probably means a commitment term: check at checkout. |
| OVHcloud | VPS-2 | 4 vCore / 8 GB / 75 GB | from €7.21 ex VAT | | |
| **Hetzner** | **CPX22** (shared AMD) | 2 vCPU / 4 GB / 80 GB NVMe | **€16.99 ex VAT (Helsinki)**, €19.99 (Nuremberg) | Falkenstein, Nuremberg, Helsinki | Hourly billing, good API, snapshots €0.0143/GB, backups +20% (page: "from €1.098"). 20 TB traffic. |
| Hetzner | CX23 (shared) / CAX11 (ARM) | 2 vCPU / 4 GB / 40 GB | €5.99 / €6.49 ex VAT | Nuremberg, Helsinki | **Can't be ordered now.** Every Cost-Optimized plan page says "This product is currently unavailable. Please check back later." Third-party reports say this has held since at least August 2026, after Hetzner's price rises in April and June 2026. Take one if it comes back. |
| Hetzner | CCX13 (dedicated) | 2 dedicated vCPU / 8 GB / 80 GB | €36.99 (HEL) / €43.49 (NBG) ex VAT | | Overkill. |
| **Contabo** | Cloud VPS 4 (smallest) | 4 vCPU / 8 GB / 100 GB SSD | about **€4.40** (24-month term, incl. VAT; the page text was garbled, headline €5.50) | Germany and others | Setup fee on monthly terms. A lot of hardware for the money, but known for crowded hosts. Fine for a hobby site, with uneven bot speed. |
| **DigitalOcean** | Basic 4 GiB | 2 vCPU / 4 GiB / 80 GiB | **$24** | Frankfurt, Amsterdam | IPv4 included; backups +20% (weekly) or +30% (daily). |
| **Akamai (Linode)** | Linode 4 GB (shared) | 2 vCPU / 4 GB / 80 GB | **$24** | Frankfurt, Milan, Paris, Amsterdam, Stockholm (from Akamai's region list; the pricing page didn't show them) | 4 TB transfer. |
| **Scaleway** | PLAY2-NANO / DEV1-M | 2 vCPU / 4 GB; DEV1-M 3 vCPU / 4 GB | about **€20.10** / **€14.74** ex VAT (from search snippets of the pricing page; the page itself refused the fetch) | Paris, Amsterdam, Warsaw | A public IPv4 costs extra. |

### 2b. Container platforms (they run your Docker image)

These all need **one instance always on**, with no scale-to-zero, since
tables live in memory. That makes them several times dearer than a VPS.

| Platform | Shape | Monthly cost | EU region | WebSockets | Persistent storage | TLS |
|---|---|---|---|---|---|---|
| **Fly.io** | shared-cpu-2x + 2 GB extra = 4 GB | **≈ $25.40** in iad; Frankfurt runs about 15% higher (shared-cpu-1x 1 GB: $7.73 fra vs $6.70 iad), so **≈ $29** | Frankfurt (fra), Amsterdam | Yes (Fly proxy) | Fly Volumes **$0.15/GB/mo**, tied to one machine; snapshots $0.08/GB (first 10 GB free) | Let's Encrypt; first 10 hostnames free, then $0.10/mo each |
| Fly.io | performance-2x, 4 GB (dedicated) | **$66** (iad), ≈ $76 fra | | | | |
| **Railway** | billed on **measured** use: $20 per vCPU-month, $10 per GB-month | for this site's use (≈1.3 GB, mostly idle CPU) about **$15–25**; reserving all of 2 vCPU / 4 GB would cost **≈ $80** | EU West (Amsterdam) | Yes | Volumes $0.15/GB/mo (Hobby: max 5 GB) | Managed certificates on custom domains (Hobby: 2 domains) |
| **Render** | Pro (2 CPU / 4 GB); Standard (1 CPU / 2 GB) | **$85** / **$25**, plus disk **$0.25/GB/mo** | Frankfurt | Yes | Persistent disk. A service with a disk runs one instance and gets no zero-downtime deploys, which suits this site anyway. | Managed, free |
| **Google Cloud Run** | 2 vCPU / 4 GiB, min = max = 1 instance, instance-based billing | **≈ $109** at Tier 1 rates ($0.000018/vCPU-s, $0.000002/GiB-s, after 240k vCPU-s + 450k GiB-s free). The pricing page didn't render; the rates come from search snippets of it. | europe-west1/3/4, Milan (europe-west8) | Yes, but **each connection is cut after the request timeout (max 60 min)**. The client reconnects in 2 s, so play survives a blip. | **No disk.** Only Cloud Storage FUSE or NFS mounts, where a rename isn't atomic, and `db.py` relies on renames. Not recommended. | Managed |
| **Azure Container Apps** | 2 vCPU / 4 GiB, min 1 replica | **≈ $150** if always "active" ($0.000024/vCPU-s + $0.000003/GiB-s), down to **≈ $47** at the idle rate. A new "Environment Management Hour" meter at **$0.10/h** (effective 2026-11-01) appears in the price list; if it applies, add about $72. | **Austria East**, Italy North, Germany West Central | Yes | Azure Files mount (SMB), billed apart | Free managed certificates |

### 2c. Free tier: Oracle Cloud Always Free (ARM)

- **Allowance today:** 1,500 OCPU-hours and 9,000 GB-hours a month of
  `VM.Standard.A1.Flex`, which equals **2 OCPUs + 12 GB RAM** (it used
  to be 4 + 24). Also 200 GB of block storage, all in your **home
  region**, which you pick once at sign-up. EU regions: Frankfurt,
  Amsterdam, Zurich, Milan, Paris, Marseille, Madrid, Stockholm. That
  list is from Oracle's region list as I know it; its pages refused the
  fetch today.
- **Idle reclamation:** Oracle may take back an Always Free instance if,
  over 7 days, CPU (95th percentile), network **and** memory (A1) all stay
  **below 20%**. This site idles at about 1.3 of 12 GB (11%) with almost
  no CPU between games, **so it would qualify for reclamation**. The usual
  fix is to upgrade the account to Pay As You Go. You still pay nothing
  within the free allowance, but it needs a card on file.
- **Capacity:** A1 machines are often "out of capacity" in popular home
  regions, and Frankfurt is one of them.
- **ARM support:** **jaxlib 0.12.1 ships `manylinux_2_27_aarch64` wheels
  for cp312–cp315**, cp314 included, and the JAX page lists Linux aarch64
  CPU as supported. pyspiel is plain C++ with pybind11 and builds on
  aarch64 with gcc or clang. One risk: a pinned dependency without an
  aarch64 wheel (check `tensorstore`, `ml_dtypes`, `jaxlib==0.12.0.1`).
  To check before you rely on it, run
  `docker buildx build --platform linux/arm64 .` locally. It is slow
  under emulation, but proves the image builds. The trained models are
  plain arrays and load the same on ARM.
- **Verdict:** a fine free playground. It's risky for something friends
  rely on: reclamation, capacity, and an ARM-only image to maintain.

### 2d. Option zero: keep the laptop and add a Cloudflare Tunnel (€0 plus a domain)

Not a provider, but the cheapest way to get a public HTTPS address.
`cloudflared` runs in WSL and opens an **outbound** tunnel to
Cloudflare, so you need no portproxy, no firewall rule, no router port
forward and no public IP. Cloudflare provides the certificate, and
**Cloudflare Access** (free up to 50 users) can put an e-mail login in
front of the watch subdomain. The catch: the laptop must stay on and
awake. Tunnel config sketch (`~/.cloudflared/config.yml`):

```yaml
tunnel: schnaps
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: schnaps.example.eu
    service: http://localhost:8000
  - hostname: watch.schnaps.example.eu   # protect with Cloudflare Access
    service: http://localhost:8001
  - service: http_status:404
```

## 3. Domain name

| Registrar | `.eu` | `.com` | `.at` | Notes |
|---|---|---|---|---|
| **Porkbun** | **$5.88** reg = renew | $11.81 reg = renew | not listed | USD, all fees included. `.org` $11.84, `.net` $12.52, `.xyz` $1.29 the first year, then about $14.21. |
| **Cloudflare Registrar** | at cost | at cost (no markup; the per-TLD table didn't render) | not verified | Needs the domain's DNS on Cloudflare, which is free. |
| **INWX** (Berlin) | $11.30 | $15.72 | **$14.40** | Discount-tier prices before VAT; the page lists no renewal prices for these. |

`.it` needs an EU resident, which you are; most registrars sell it for
about €10–15 a year. **Cheapest sensible choice: a `.eu` at Porkbun, about
€5.50 a year (≈ €0.46 a month).** A free subdomain such as DuckDNS also
works with Let's Encrypt, but looks less tidy.

## 4. HTTPS

### 4a. On a VPS: Caddy (recommended)

Caddy gets and renews Let's Encrypt certificates on its own. It needs
ports 80 and 443 open and DNS A/AAAA records pointing at the VPS. It
proxies WebSockets with no extra settings. Run the site on localhost
only (`SCHNAPS_WEB_HOST=127.0.0.1`, or don't publish 8000/8001 from
Docker), and put the watch app on its own subdomain behind a password.

```caddyfile
# /etc/caddy/Caddyfile
{
    email you@example.eu          # Let's Encrypt account e-mail
}

schnaps.example.eu {
    encode zstd gzip

    # FastAPI's API docs are on by default; hide them.
    @apidocs path /docs* /redoc* /openapi.json
    respond @apidocs 404

    request_body {
        max_size 64KB
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options    "nosniff"
        Referrer-Policy           "no-referrer"
        X-Frame-Options           "DENY"
        # Try this in report-only mode first; inline styles may need it.
        Content-Security-Policy   "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self' wss://schnaps.example.eu"
    }

    # REST and the WebSocket /ws/tables/{id} both go to uvicorn;
    # Caddy upgrades WebSocket connections by itself.
    reverse_proxy 127.0.0.1:8000
}

# The all-cards view: every hand face up. Never public without a password.
# Only needed if you turn the watch app back on (SCHNAPS_WEB_WATCH_PORT=8001);
# the planned image has it off (section 8).
watch.schnaps.example.eu {
    basic_auth {
        # caddy hash-password --plaintext '...'
        family $2a$14$REPLACE_WITH_HASH
    }
    reverse_proxy 127.0.0.1:8001
}
```

Stock Caddy has no rate limiting. Use the `caddy-ratelimit` plugin
(build with `xcaddy build --with github.com/mholt/caddy-ratelimit`),
Cloudflare's free rate-limiting rule, or nginx (below).

### 4b. On a VPS: nginx + certbot (built-in rate limiting)

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=api:10m  rate=10r/s;

server {
    listen 443 ssl; listen [::]:443 ssl; http2 on;
    server_name schnaps.example.eu;
    ssl_certificate     /etc/letsencrypt/live/schnaps.example.eu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/schnaps.example.eu/privkey.pem;
    client_max_body_size 64k;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location ~ ^/(docs|redoc|openapi\.json) { return 404; }

    location ~ ^/api/(login|accounts)$ {          # PBKDF2: expensive
        limit_req zone=auth burst=5 nodelay;
        proxy_pass http://127.0.0.1:8000;
    }
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
    }
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 1h;                    # client pings every 25 s
        access_log off;                           # the seat token is in the query string
    }
    location / { proxy_pass http://127.0.0.1:8000; }
}
server { listen 80; listen [::]:80; server_name schnaps.example.eu; return 301 https://$host$request_uri; }
```

Get the certificate with `certbot --nginx -d schnaps.example.eu`; the
certbot package installs a systemd timer that renews it. Add a second
`server` block for `watch.` with `auth_basic`, proxying to 8001.

### 4c. On the container platforms

Fly.io, Render, Railway, Cloud Run and Azure Container Apps all issue and
renew certificates for a custom domain on their own. You add a CNAME or
A record and they do the rest; Fly charges $0.10 a month per hostname
after the first 10. Each platform exposes **one HTTP port per app**, so
the watch app (8001) needs a second app/service or must stay off
(`SCHNAPS_WEB_WATCH_PORT=0`). Most platforms can't put a password on it
for you.

### 4d. Cloudflare in front (Free plan)

- WebSockets are proxied on **every plan, Free included**, with no extra
  settings. Idle connections close after about 100 s; the client's 25 s
  ping keeps them open.
- Turn the DNS record's proxy on, and set SSL mode to **Full (strict)**.
  The origin then needs a valid certificate: Caddy's Let's Encrypt one
  works, or a free **Cloudflare Origin CA** certificate (up to 15 years,
  trusted by Cloudflare only).
- Cloudflare proxies only certain ports (HTTPS: 443, 2053, 2083, 2087,
  2096, 8443). **8001 is not among them**, so serve the watch app on a
  subdomain on 443 and don't expose its port.
- Extras on Free: DDoS shielding, the origin IP stays hidden (firewall
  the VPS so it accepts 80/443 only from Cloudflare's ranges), and
  rate-limiting / WAF rules. Behind Cloudflare, have Caddy trust
  Cloudflare's IPs (`trusted_proxies`) so rate limits see the real
  client address.

## 5. Deployment

### 5a. The Docker image

The real files are in **`deploy/`**; the README's "The Docker image"
section has the commands.

- **`deploy/Dockerfile`**, in three stages:
  1. Node 22 builds the client.
  2. `python:3.14-slim-trixie` with build-essential, cmake and ninja
     compiles only `python/pyspiel.so`. It builds from the **local**
     `open_spiel/` tree (uncommitted schnaps changes included), whose
     C++ dependencies `install.sh` already fetched, so nothing is
     downloaded.
  3. The runtime: `python:3.14-slim-trixie` with the laptop venv's exact
     packages (`deploy/requirements.txt`), the OpenSpiel Python package,
     `pyspiel.so`, the server, the models and `client/dist`. It runs as a
     non-root user (uid 1000) with a health check on `/api/site`.
- **Build context:** the `Docker/` folder, so the build sees both
  `open_spiel/` and `schnaps-web/`. **`deploy/Dockerfile.dockerignore`**
  is an allowlist that sends only those parts: none of `venv/`, `build/`,
  `node_modules/`, `.git`, `data/`, or the 600 MB of OpenSpiel GUI and
  JSON test files.
- **Build on the laptop** (Docker Desktop) and ship the image with
  `docker save … | ssh … docker load`. A 2-vCPU VPS would take a long
  time to compile OpenSpiel, and the models aren't in git.
- **Settings baked in** (section 8): `SCHNAPS_WEB_WATCH_PORT=0`,
  `SCHNAPS_WEB_MAX_TABLES=8`, `SCHNAPS_WEB_LOGIN_RATE=10`,
  `SCHNAPS_WEB_DB_DIR=/data/db`. Override any of them with `-e`.
- **`deploy/docker-compose.yml`** runs the image and Caddy together. The
  site's port isn't published: Caddy reaches it on the compose network,
  so `FORWARDED_ALLOW_IPS: "*"` is safe there. Caddy publishes 80 and
  443, and its certificates live in a named volume. **`deploy/Caddyfile`**
  takes the domain from `SCHNAPS_DOMAIN` in `.env`.
- To build for ARM (Oracle), use
  `docker buildx build --platform linux/arm64`; section 2c lists the
  risks.

### 5b. What persists, and backups

The paths below assume the compose files are in `/srv/schnaps`.

- **Models:** they're in the image. Mount them read-only from
  `/srv/schnaps/models` if you want to swap a checkpoint without a
  rebuild.
- **`data/db`:** on the host folder `/srv/schnaps/data/db` (`./data`
  next to `docker-compose.yml`), which
  survives container rebuilds. Copy the laptop's `schnaps.db` there once
  with `scp` (with the site stopped) to keep the existing accounts and
  ratings.
- **Tables** are in memory, so a restart or deploy ends running games, as
  it does today. Deploy when nobody is playing.
- **Backups:** the database is one small SQLite file. A nightly cron job
  on the VPS is enough. It uses SQLite's online backup, which is safe while
  the site runs; a plain `cp` could catch a write half done. Install the
  `sqlite3` package on the host for this.

  ```bash
  # /etc/cron.d/schnaps-backup: 04:00 every night, keep 30 days
  0 4 * * * root sqlite3 /srv/schnaps/data/db/schnaps.db ".backup /srv/backup/db-$(date +\%F).sqlite" && find /srv/backup -name 'db-*.sqlite' -mtime +30 -delete
  ```

  Then pull it off the machine: `rsync` or `scp` from the laptop, or
  `restic` to a cheap bucket or a Hetzner Storage Box. The file holds
  password hashes, so keep the copies private or encrypt them (restic
  encrypts by default). Provider backups (Hetzner
  +20%, DigitalOcean +20/30%, OVH's included daily backup, netcup
  snapshots) cover the rest of the machine.
- **Updates:** turn on `unattended-upgrades` for the OS, and rebuild the
  image now and then for Python package security fixes.

## 6. Security before going public

The site was built for a trusted LAN. Here is what to change, from
reading the code. Nothing has been changed. "Proxy" means it can be done
in Caddy, nginx or Cloudflare without touching the code; "Code" means it
needs a change in `schnaps-web`.

| # | Issue | Why it matters in public | Fix |
|---|---|---|---|
| 1 | **The watch app on 8001 shows every hand** | Anyone could cheat by watching it in another tab. | Proxy: password on a separate subdomain (basic auth or Cloudflare Access), or `SCHNAPS_WEB_WATCH_PORT=0`. Never publish 8001 directly. |
| 2 | **Plain HTTP** | Passwords and device keys travel in clear text today; the README warns about it. | Proxy: HTTPS only, HTTP redirected to HTTPS, HSTS (section 4). |
| 3 | **No rate limit on `/api/login` and `/api/accounts`** | Both run 200,000-round PBKDF2 **synchronously inside an async handler** (`db.py` `login`/`register`), so each attempt blocks the event loop and every table for about 0.1–0.3 s. A login flood freezes all games, and nothing stops password guessing. | Proxy: e.g. 10 per minute per IP (nginx config above). Code (later): run the hash in `asyncio.to_thread`, and lock out after repeated failures. |
| 4 | **Open registration with no limit** | A script can create thousands of accounts, filling the database with junk names. (Since the move to SQLite, key lookups are indexed, so size alone no longer slows requests down.) | Proxy: rate limit (as #3). Code: an invite code or a simple sign-up question for public registration. |
| 5 | **Anyone can start up to 50 tables of four bots** (`max_tables=50`) | Bot play, Napoli most of all, would saturate 2 vCPUs, and every human table would lag. | Setting: `SCHNAPS_WEB_MAX_TABLES=6..8`; lower `SCHNAPS_WEB_SEARCH_SAMPLES` or set it to 0 to drop Napoli. Code: only logged-in users may create tables, at most one each. |
| 6 | **Weak passwords allowed** (`PASSWORD_MIN = 4`) | Easy to guess, even rate-limited. | Code: minimum 8–10 characters. |
| 7 | **Device keys pile up** (a new key on every login, never expired) | A stolen key works forever, and the list keeps growing. | Code: expire keys (e.g. 180 days) and cap their number per user. The "Log out" button already deletes one key. |
| 8 | **Keys sit in `localStorage`** and go in an `X-User-Key` header; there are no cookies | Good news: "secure cookies", SameSite and CSRF **don't apply**, because nothing is sent automatically. The risk moves to XSS: a script injected into the page could read the key. React escapes nicknames, so today's risk is low. | Proxy: a Content-Security-Policy header (section 4a) as a second line of defence. |
| 9 | **CORS** | There is no `CORSMiddleware`, so other sites' scripts can't read the API. That's the right setting: **keep it that way** and don't add `allow_origins=["*"]`. The WebSocket doesn't check `Origin`, but without a seat token it only shows what any spectator sees. | Proxy (optional): reject `/ws/` when `Origin` isn't your domain. |
| 10 | **Seat token in the WebSocket URL** (`?token=`) | It lands in proxy access logs. | Proxy: turn off access logs for `/ws/` (nginx above), or strip query strings from logs. |
| 11 | **FastAPI's `/docs`, `/redoc` and `/openapi.json` are on** | They list every endpoint. Not secret, but there's no need to advertise them. | Proxy: return 404 (section 4). Code: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. |
| 12 | **No request size limit** | Large JSON bodies cost memory. | Proxy: 64 KB limit (`request_body` / `client_max_body_size`). |
| 13 | **Listens on 0.0.0.0** (for the LAN) | On a VPS, uvicorn would face the internet directly, without TLS or limits. | Setting: `SCHNAPS_WEB_HOST=127.0.0.1`, or Docker `127.0.0.1:` port bindings. Firewall: allow only 22, 80 and 443. |
| 14 | **No admin endpoints** | Nothing to lock down; database maintenance is done by editing files on the server. Keep it that way, or put any future admin page behind its own password (like #1). | None needed now. |
| 15 | **The server itself** | It's a public machine. | SSH keys only with password login off, `fail2ban`, `unattended-upgrades`, and the container running as a non-root user (Dockerfile above). |
| 16 | **Privacy (GDPR)** | You store usernames, password hashes and game history of people in the EU. | A short privacy note on the site (what is stored, how to delete an account); Austrian law may also want an imprint (Impressum) on a public site. Keep the user count small and known. |

**Minimum before opening it to friends over the internet:** #1, #2, #3,
#5 and #13. All five are settings or proxy configuration, with no code
change. #4, #6 and #7 matter once strangers can find the site.

## 7. Recommendation and total cost

**Recommended: netcup VPS 500 G12.5 (2 vCore x86, 4 GB, 64 GB), Vienna,
with Docker, Caddy and a `.eu` domain.**

| Item | Monthly |
|---|---|
| netcup VPS 500 G12.5, 12-month term: €6.94 net, ≈ **€8.33 with 20% AT VAT** (1-month term: ≈ €9.58) | €8.33 |
| Vienna location (+€1.04; "no preference Europe" is free) | €1.04 |
| `.eu` domain at Porkbun, $5.88 a year | ≈ €0.46 |
| Let's Encrypt via Caddy | €0 |
| Backups: cron + rsync to the laptop (netcup snapshots included) | €0 |
| **Total** | **≈ €9.80 a month** (about €11 on monthly terms) |

Why this one:

- Its 4 GB RAM is three times the measured 1.3 GB, and 2 vCPU is enough
  for a few tables with bots.
- It's x86, so the image built on the laptop runs as it is.
- Vienna is the closest data centre to Austria and Italy, which gives
  the lowest latency.
- It has a flat price and no metered surprises, unlike Fly, Railway,
  Cloud Run or Azure.

**Alternatives:**

- **Hetzner CPX22, Helsinki: ≈ €20.40 a month with VAT** (€16.99 ex
  VAT), or **€21.40 with backups added at 20%**. Choose it for hourly
  billing, a good API and console, and one-click snapshots. If the
  CX23 (€5.99 ex VAT) becomes orderable again, it is the best deal of
  all at about €7.20 with VAT.
- **OVH VPS-1: from €3.81 ex VAT (≈ €4.60 with VAT)**. The cheapest
  found, with a daily backup included. Check the commitment term and the
  location at checkout.
- **Fly.io, shared-cpu-2x with 4 GB in Frankfurt: ≈ $29 a month** plus
  $0.15 for a 1 GB volume. Choose it if you want no server to look after.
  Shared CPUs on Fly are throttled after bursts, so Napoli may slow down;
  the watch app needs a second app.
- **€0: keep the laptop and add a Cloudflare Tunnel** (section 2d) plus
  the domain, ≈ €0.46 a month. It works as long as the laptop is on.
- **Oracle Always Free: €0**, but it's ARM, needs a card, may be
  reclaimed when idle, and is often out of capacity. Good for
  experiments, not for a site friends rely on.

**Not recommended:** Cloud Run (≈ $109, no real disk, WebSockets cut
after 60 min), Azure Container Apps (≈ $47–150 plus a possible
management fee), Render Pro ($85) and DigitalOcean or Akamai ($24, fine
but more than twice netcup's price for the same size).

## 8. Decisions (2026-11-25)

1. **Watch port (8001): off in the image.** The Dockerfile sets
   `SCHNAPS_WEB_WATCH_PORT=0`, exposes only 8000, and the compose file
   publishes only 8000. Locally, `scripts/start_site.sh` doesn't set the
   variable, so 8001 keeps working on the laptop. To turn it on in a
   container later, pass `-e SCHNAPS_WEB_WATCH_PORT=8001` and put it
   behind a password (section 4a).
2. **HTTPS is not in the Dockerfile.** The image serves plain HTTP on
   8000, and a proxy in front handles HTTPS. On a VPS that's Caddy on the
   same machine: free certificates, about 30–50 MB RAM. On Cloudflare or
   a container platform it's their edge. **None of these adds cost.**
   This is the usual split, and it keeps the image the same for local
   tests and for the server. The app needs nothing for it: the client
   picks `wss://` from the page's scheme, and the server builds no
   absolute URLs. One setting matters if the app ever needs the visitor's
   IP address (for example, rate limiting inside the app). uvicorn takes
   the client address from `X-Forwarded-For` only from proxies it
   trusts: 127.0.0.1 by default, set by the `FORWARDED_ALLOW_IPS`
   environment variable. Behind Docker the proxy arrives from the bridge
   address, hence `FORWARDED_ALLOW_IPS` in the compose file. Set this
   only when the app port isn't reachable from outside (point 5).
3. **Rate-limit login and registration: done in the app.**
   `POST /api/login` and `POST /api/accounts` allow at most
   `SCHNAPS_WEB_LOGIN_RATE` requests per client address in any 60
   seconds. More get 429 "too many attempts; try again in a minute",
   translated in the client. It is 0 (off) unless set, so tests and the
   LAN don't notice it; the image sets 10. The PBKDF2 hash now runs in
   a worker thread (`asyncio.to_thread`), so a burst of logins no longer
   stalls the tables. The limit works wherever the image runs, with no
   proxy plugin needed. Behind a proxy, uvicorn must trust its
   `X-Forwarded-For` (`FORWARDED_ALLOW_IPS`, set in the compose file), or
   every visitor would count as the proxy's address.
4. **At most 8 tables:** `SCHNAPS_WEB_MAX_TABLES=8` in the image.
   Locally the default stays 50 unless you set it.
5. **Listening only behind the proxy, and local play.** This is the
   other half of point 2. HTTPS and rate limits live in the proxy, so on
   a public server the app's port must be reachable **only** through the
   proxy. Otherwise anyone could bypass both at `http://<server>:8000`.
   The restriction goes in the **deployment**, not the code: the compose
   file publishes `127.0.0.1:8000:8000`, so only Caddy on the same
   machine reaches it, and the VPS firewall opens only 22, 80 and 443.
   Inside the container the app still listens on 0.0.0.0, as it must.
   **Local play doesn't change.** `scripts/start_site.sh` keeps
   0.0.0.0:8000 and 8001 for the LAN, as today. To test the image
   itself on the laptop, run it with the ports open:

   ```bash
   docker run --rm -p 8000:8000 -v "$PWD/data:/data" schnaps
   # with the watch app:
   docker run --rm -p 8000:8000 -p 8001:8001 -e SCHNAPS_WEB_WATCH_PORT=8001 \
     -v "$PWD/data:/data" schnaps
   ```

## Sources (all read 2026-11-25)

VPS:
- Hetzner Cost-Optimized (CX/CAX): https://www.hetzner.com/cloud/cost-optimized/
- Hetzner Regular Performance (CPX): https://www.hetzner.com/cloud/regular-performance/
- Hetzner General Purpose (CCX): https://www.hetzner.com/cloud/general-purpose/
- Hetzner 2026 price rises and CX availability (third-party): https://www.tomshardware.com/tech-industry/hetzner-to-raise-prices-by-up-to-37-percent-from-april-1 , https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/ , https://findstack.com/resources/hetzner-price-increase-2026
- netcup VPS: https://www.netcup.com/en/server/vps and the VPS 500 configurator https://www.netcup.com/de/server/vps/vps-500-g12.5-24m-eu
- OVHcloud VPS: https://www.ovhcloud.com/en-ie/vps/
- Contabo Cloud VPS: https://contabo.com/en/vps/
- DigitalOcean Droplets: https://www.digitalocean.com/pricing/droplets
- Akamai / Linode: https://www.akamai.com/cloud/pricing/cpu (redirected from https://www.linode.com/pricing/)
- Scaleway (page refused the fetch; figures from search snippets of it): https://www.scaleway.com/en/pricing/virtual-instances/
- Vultr: not read (the page refused the fetch).

Container platforms:
- Fly.io: https://docs.fly.io/about/pricing
- Railway: https://railway.com/pricing
- Render (figures from https://render.com/pricing.md and search snippets): https://render.com/pricing
- Google Cloud Run (page didn't render; rates from search snippets): https://cloud.google.com/run/pricing ; WebSockets: https://docs.cloud.google.com/run/docs/triggering/websockets
- Azure Container Apps: https://azure.microsoft.com/en-us/pricing/details/container-apps/ and the Retail Prices API (germanywestcentral): https://prices.azure.com/api/retail/prices?$filter=serviceName%20eq%20%27Azure%20Container%20Apps%27%20and%20armRegionName%20eq%20%27germanywestcentral%27

Free tier and ARM:
- Oracle Always Free resources: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm (https://www.oracle.com/cloud/free/ refused the fetch)
- jax / jaxlib wheels: https://pypi.org/project/jax/ , https://pypi.org/project/jaxlib/#files

Domains:
- Porkbun: https://porkbun.com/products/domains
- Cloudflare Registrar: https://www.cloudflare.com/products/registrar/
- INWX: https://www.inwx.com/en/domain/pricelist

Cloudflare:
- WebSockets: https://developers.cloudflare.com/network/websockets/
- Proxied ports: https://developers.cloudflare.com/fundamentals/reference/network-ports/
