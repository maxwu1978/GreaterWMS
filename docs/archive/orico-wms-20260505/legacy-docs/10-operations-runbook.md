# Operations Runbook

Production operations guide for WMS QuickStart.

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Render.com                            │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ wms-backend  │  │  PostgreSQL  │  │    Redis     │  │
│  │  (FastAPI)   │──│    16        │  │     7        │  │
│  │  port 8000   │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────┐
│      Vercel         │
│  ┌───────────────┐  │
│  │   Frontend    │  │
│  │  React SPA    │  │
│  └───────────────┘  │
└─────────────────────┘
```

**Domains**:
- API: `api.maxsmartwms.online`
- App: `app.maxsmartwms.online`

---

## Health Checks

### Backend Health
```bash
curl https://api.maxsmartwms.online/health
# Expected: {"status": "ok"}
```

### Database Connectivity
```bash
# Via Render shell or local with DATABASE_URL
uv run python -c "
import asyncio
from app.core.database import engine
async def check():
    async with engine.connect() as conn:
        result = await conn.execute('SELECT 1')
        print('DB OK:', result.scalar())
asyncio.run(check())
"
```

### Redis Connectivity
```bash
redis-cli -u $REDIS_URL ping
# Expected: PONG
```

---

## Common Operations

### Deploy New Version
1. Push to `main` branch
2. Render auto-deploys from main (configured in render.yaml)
3. Monitor deploy logs in Render dashboard
4. Verify health check after deploy

### Run Database Migration
```bash
# On Render shell:
cd /opt/render/project/src/backend
alembic upgrade head

# Or via local machine with production DATABASE_URL:
DATABASE_URL=postgresql+asyncpg://... uv run alembic upgrade head
```

### Rollback Migration
```bash
alembic downgrade -1    # rollback last migration
alembic history         # view migration history
```

### Seed Demo Data
```bash
uv run python seed.py
```

### Check Active Sessions / Connected Users
```bash
# Check Redis for active WebSocket sessions
redis-cli -u $REDIS_URL keys "ws:*"
```

---

## Environment Variables (Production)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL asyncpg connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `JWT_SECRET_KEY` | Yes | Token signing secret (MUST be set, or startup fails) |
| `DEBUG` | No | Set to `false` in production |
| `CORS_ORIGINS` | Yes | JSON array of allowed frontend origins |
| `STRIPE_SECRET_KEY` | No | Stripe billing integration |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook verification |
| `DEEPSEEK_API_KEY` | No | AI agent - DeepSeek provider |
| `MINIMAX_API_KEY` | No | AI agent - MiniMax provider |
| `QWEN_API_KEY` | No | AI agent - Qwen provider |
| `KIMI_API_KEY` | No | AI agent - Kimi provider |

---

## Monitoring & Logs

### Render Logs
- Access via Render dashboard → Service → Logs
- Logs include: request timing, tenant context, errors

### Request Logging
The `RequestLoggingMiddleware` logs every request:
```
INFO: tenant=<uuid> method=GET path=/api/v1/inventory status=200 duration=45ms
```

### Rate Limiting
- Default: 120 requests/minute per IP
- Configurable via `RateLimitMiddleware`
- Returns `429 Too Many Requests` when exceeded

---

## Troubleshooting

### JWT Token Issues
**Symptom**: Users getting 401 after deploy
**Cause**: JWT_SECRET_KEY changed or missing
**Fix**: Ensure `JWT_SECRET_KEY` env var is set and consistent across deploys. Key must not change or all existing tokens become invalid.

### Database Connection Pool Exhaustion
**Symptom**: `TimeoutError` or slow responses
**Cause**: Too many concurrent connections
**Fix**:
1. Check connection count: `SELECT count(*) FROM pg_stat_activity;`
2. Kill idle connections: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';`
3. Consider increasing pool size in SQLAlchemy config

### RLS Policy Blocking Queries
**Symptom**: Empty results when data should exist
**Cause**: tenant_id context not set correctly
**Fix**: Verify `_current_tenant_id` is being set in `get_db_session()`. Check that the JWT token contains the correct `tenant_id` claim.

### Frontend CORS Errors
**Symptom**: Browser console shows CORS blocked
**Cause**: Frontend origin not in `CORS_ORIGINS`
**Fix**: Update `CORS_ORIGINS` env var on Render to include the new origin. No code change needed.

### Alembic Migration Conflicts
**Symptom**: `alembic upgrade head` fails with "multiple heads"
**Fix**:
```bash
alembic heads          # see conflicting heads
alembic merge heads -m "merge migrations"   # create merge
alembic upgrade head   # apply
```

### WebSocket Disconnections
**Symptom**: Scanner or AGV WebSocket drops frequently
**Cause**: Render's proxy timeout (default 60s for idle connections)
**Fix**: Implement heartbeat/ping in client (every 30s). The `useWebSocket` hook should handle reconnection automatically.

---

## Backup & Recovery

### Database Backup
Render provides automatic daily backups for PostgreSQL. Manual backup:
```bash
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

### Database Restore
```bash
psql $DATABASE_URL < backup_20260505.sql
```

### Point-in-Time Recovery
Available via Render dashboard for the PostgreSQL instance.

---

## Security Checklist

- [ ] `JWT_SECRET_KEY` is a strong random value (not default)
- [ ] `DEBUG=false` in production
- [ ] `CORS_ORIGINS` only includes known frontend domains
- [ ] Database credentials rotated periodically
- [ ] Stripe webhook secret configured for payment security
- [ ] Rate limiting active (120 req/min default)
- [ ] RLS policies verified (run `test_multi_tenant_isolation` test)

---

## Scaling Considerations

### Current Limits
- Single Render instance (no horizontal scaling yet)
- PostgreSQL connection pool: default 20 connections
- Redis: single instance, no cluster

### When to Scale
- Sustained >80% CPU on API service → add instances
- Database connection pool exhaustion → increase pool or add read replicas
- Redis memory >80% → upgrade or add eviction policy

### Scaling Steps
1. Render: change plan tier for more CPU/RAM
2. Add more web service instances (stateless, share DB + Redis)
3. For read-heavy loads: add PostgreSQL read replica
4. For background tasks: separate worker service (Celery + Redis)
