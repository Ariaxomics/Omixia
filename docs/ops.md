# Omixia — Operations Guide

## Secret Rotation Procedure

### 1. FLASK_SECRET_KEY

Rotating the Flask secret key invalidates **all active sessions** — users will be logged out.

```bash
# Generate a new key (≥32 random bytes)
python -c "import secrets; print(secrets.token_hex(32))"

# Update backend/.env
FLASK_SECRET_KEY=<new-value>

# Restart the app container
docker compose -f backend/docker-compose.yml restart app
```

**Impact**: All active user sessions are immediately invalidated.

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

# 3. Restart the app container (mongo container does NOT need restart)
docker compose -f backend/docker-compose.yml restart app
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
| `FLASK_SECRET_KEY` | Yes | Session signing key — must be long and random |
| `FLASK_DEBUG` | No | Set `0` in production always |
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

# Restart a single service
docker compose -f backend/docker-compose.yml restart app
docker compose -f backend/docker-compose.yml restart nginx

# View logs
docker compose -f backend/docker-compose.yml logs -f app

# Reload demo data
docker exec app_omixia flask load-demo
```

---

## Health Check

```bash
curl https://api.yourdomain.com/api/v1/health
# Expected: {"service": "omixia", "status": "ok"}
```
