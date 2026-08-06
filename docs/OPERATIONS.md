# Omixia — Operations Guide

## Secret Rotation Procedure

### 1. FLASK_SECRET_KEY

Signs the session cookie. The `FLASK_` prefix is historical — the backend is FastAPI; the name was kept so existing `.env` files keep working. It is read into `settings.SECRET_KEY`.

Rotating it invalidates **all active sessions** — users will be logged out.

```bash
# Generate a new key (≥32 random bytes)
python -c "import secrets; print(secrets.token_hex(32))"

# Update backend/.env
FLASK_SECRET_KEY=<new-value>

# Recreate the app container (restart alone will not reload workers reliably)
docker compose -f backend/docker-compose.yml up -d --force-recreate app
```

**Impact**: All active user sessions are immediately invalidated. Existing Redis session records are orphaned rather than deleted, and expire on their own 7-day TTL.

---

### 2. MongoDB root password

```bash
# 1. Connect to the running mongo container and change the password
docker exec -it mongo_omixia mongosh \
  -u admin -p <old-password> --authenticationDatabase admin \
  --eval 'db.adminCommand({ updateUser: "admin", pwd: "<new-password>" })'

# 2. Update backend/.env — both variables must match
MONGO_INITDB_ROOT_PASSWORD=<new-password>
MONGO_URI=mongodb://admin:<new-password>@mongo:27017/admin?authSource=admin

# 3. Recreate the app container (mongo container does NOT need restart)
docker compose -f backend/docker-compose.yml up -d --force-recreate app
```

**Note**: `MONGO_INITDB_ROOT_PASSWORD` is only used by MongoDB on first initialisation. After the container exists, use the `updateUser` command above to change the password.

---

### 3. Redis

Redis is not password-protected by default in this deployment (internal Docker network only). If you add `requirepass` to the Redis config:

```bash
# Update backend/.env
CACHE_REDIS_URL=redis://:<new-password>@redis:6379/0

# Restart app
docker compose -f backend/docker-compose.yml restart app
```

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Session signing key — must be long and random. Historical name; read into `settings.SECRET_KEY`. |
| `FLASK_DEBUG` | No | Set `0` in production always. Historical name; read into `settings.DEBUG`. |
| `SESSION_COOKIE_NAME` | No | Session cookie name (this deployment uses `Omixia`) |
| `MONGO_INITDB_ROOT_USERNAME` | Yes | MongoDB admin username (used at init) |
| `MONGO_INITDB_ROOT_PASSWORD` | Yes | MongoDB admin password |
| `MONGO_URI` | Yes | Full MongoDB connection string |
| `CACHE_REDIS_URL` | Yes | Redis connection URL |
| `OMIXIA_DB_NAME` | Yes | MongoDB database name |
| `REPORTS_BASE_PATH` | Yes | Filesystem path for PDF report storage |
| `ALLOWED_ORIGINS` | Prod | Comma-separated list of allowed CORS origins |
| `SESSION_COOKIE_SAMESITE` | Prod | Set `None` for cross-origin (Cloudflare Pages) |
| `SESSION_COOKIE_SECURE` | Prod | Set `True` when served over HTTPS |
| `SPA_BASE_URL` | Prod | URL of the React SPA (used by landing page links) |

---

## Backup and Restore

### Manual backup

```bash
./scripts/backup_mongo.sh
```

Backups are written to `./backups/` as mongodump directories named `backup_YYYYMMDD_HHMMSS`.

### Automated backup (cron)

```
0 2 * * * /home/saile/develop/Omixia/scripts/backup_mongo.sh
```

### Restore from backup

```bash
docker exec -i mongo_omixia mongorestore \
  --username admin --password <password> \
  --authenticationDatabase admin \
  /tmp/backup_YYYYMMDD_HHMMSS
```

(Copy the backup directory into the container first with `docker cp`.)

---

## Container Management

```bash
# View running containers
docker compose -f backend/docker-compose.yml ps

# Apply backend code changes (source is bind-mounted, but Gunicorn workers
# only load Python at boot — a plain `restart` is not always sufficient)
docker compose -f backend/docker-compose.yml up -d --force-recreate app

# Apply dependency changes (requirements.txt edited)
docker compose -f backend/docker-compose.yml build app
docker compose -f backend/docker-compose.yml up -d --force-recreate app

# Serve a new frontend build
docker compose -f backend/docker-compose.yml restart nginx

# View logs
docker compose -f backend/docker-compose.yml logs -f app

# Reload demo data
docker exec app_omixia python cli.py load-demo
```

### Troubleshooting: "cannot stop container: permission denied"

If Docker is installed via **snap**, `dockerd` runs under the AppArmor profile `snap.docker.dockerd`, which can lack permission to signal container processes confined by `docker-default`. Symptom: `ps`/`build`/`run`/`exec` work, but `stop`/`kill`/`rm -f` on a *running* container fail with `permission denied` — even as root.

```bash
# Confirm the cause
docker info | grep -i -A3 'security options'      # expect: apparmor
cat /proc/$(pgrep -o dockerd)/attr/current        # expect: snap.docker.dockerd (enforce)

# Workaround — kill the process directly (a root shell is unconfined)
sudo kill -9 $(docker inspect -f '{{.State.Pid}}' <container>)
docker rm <container>

# Or relax just that profile while working
sudo aa-complain /var/lib/snapd/apparmor/profiles/snap.docker.dockerd
sudo aa-enforce  /var/lib/snapd/apparmor/profiles/snap.docker.dockerd   # restore
```

Permanent fix: replace the snap with Docker CE from the official apt repo. **`snap remove docker` destroys all snap-managed volumes, including `omixia_mongo_data` — back up first.**

---

## Health Check

```bash
curl https://api.yourdomain.com/api/health
# Expected: {"status": "ok", "service": "omixia"}
```

Note the path is `/api/health`, not `/api/v1/health` — the router is named `api_v1` internally but mounts at the `/api` prefix.

Auto-generated API documentation is available at `/docs`, `/redoc`, and `/openapi.json`. Consider gating or disabling these in production via `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` in `main.py` if the API surface should not be public.
