# Vercel + Render Deployment

This project can be deployed today with:

- `Vercel` for the React frontend in [`/Volumes/MaxRelocated/WMS/frontend`](/Volumes/MaxRelocated/WMS/frontend)
- `Render` for the FastAPI backend in [`/Volumes/MaxRelocated/WMS/backend`](/Volumes/MaxRelocated/WMS/backend)
- `Render Postgres` for the primary database
- `Render Redis / Key Value` for cache and future background work

## 1. Deploy the backend on Render

Create these Render resources first:

- PostgreSQL
- Redis / Key Value
- Web Service for the backend

This repo also includes a starter Render blueprint:

- [`/Volumes/MaxRelocated/WMS/render.yaml`](/Volumes/MaxRelocated/WMS/render.yaml)

Backend service settings:

- Root Directory: `backend`
- Build Command: `pip install -e .`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Required backend environment variables:

```text
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
JWT_SECRET_KEY=<strong-random-secret>
DEBUG=false
CORS_ORIGINS=["https://your-frontend.vercel.app"]
```

Optional backend environment variables:

```text
SMTP_USER=
SMTP_PASSWORD=
EASYPOST_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

After the backend is created, run database migrations:

```bash
cd backend
alembic upgrade head
```

If you use the Render shell instead, run the same command there.

There is also a production env template here:

- [`/Volumes/MaxRelocated/WMS/backend/.env.render.example`](/Volumes/MaxRelocated/WMS/backend/.env.render.example)

## 2. Deploy the frontend on Vercel

Create a new Vercel project from this repo with:

- Root Directory: `frontend`
- Build Command: `npm run build`
- Output Directory: `dist`

Frontend environment variable:

```text
VITE_API_BASE_URL=https://your-backend.onrender.com/api/v1
```

The frontend is already wired to use `VITE_API_BASE_URL`, with `/api/v1` as a local fallback for development.

Frontend env example:

- [`/Volumes/MaxRelocated/WMS/frontend/.env.example`](/Volumes/MaxRelocated/WMS/frontend/.env.example)

## 3. Smoke test after deploy

Check these in order:

1. Backend health endpoint: `GET /health`
2. Frontend loads from Vercel
3. Registration works
4. Login works
5. Dashboard loads
6. Inventory page loads

## 4. Known limitations for this first deployment

- WebSocket endpoints exist and are better suited to Render than Vercel.
- Survey responses currently write to local disk and should eventually move to object storage or the database.
- PDF generation may need extra Render system package support depending on the exact code path used.
- CORS must include the Vercel frontend URL.
