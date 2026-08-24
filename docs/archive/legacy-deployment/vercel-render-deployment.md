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

This repo also includes a Render blueprint aligned with the current production
Docker web service:

- [`/Volumes/MaxRelocated/WMS/render.yaml`](/Volumes/MaxRelocated/WMS/render.yaml)

Backend service settings:

- Root Directory: `backend`
- Runtime: Docker
- Dockerfile Path: `./Dockerfile`
- Docker Context: `.`
- Auto Deploy Trigger: `commit`

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
EMAIL_VERIFICATION_REQUIRED=true
EMAIL_PROVIDER=brevo
EMAIL_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
BREVO_API_KEY=
BREVO_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
SMTP2GO_API_KEY=
SMTP2GO_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
MAILERSEND_API_KEY=
MAILERSEND_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
POSTMARK_SERVER_TOKEN=
POSTMARK_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
POSTMARK_MESSAGE_STREAM=outbound
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
MAILGUN_API_KEY=
MAILGUN_DOMAIN=
MAILGUN_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
MAILGUN_API_BASE_URL=https://api.mailgun.net
RESEND_API_KEY=
RESEND_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
SMTP_USER=
SMTP_PASSWORD=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
EASYPOST_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

Production transactional email should use an HTTP/API provider (`brevo`,
`smtp2go`, `mailersend`, `postmark`, `sendgrid`, `mailgun`, or `resend`). Keep
SMTP only as a manual fallback; Render has previously failed SMTP delivery with
network-level connection errors.

After the backend is created, run database migrations from the Render shell, or
from another trusted shell where the production database URL is explicitly set.
Do not run plain Alembic from a local checkout, because local `.env` values can
point at the wrong database:

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/<database>" alembic upgrade head
```

The current Render free web plan does not support Blueprint
`preDeployCommand`, so migrations remain an explicit operator step unless the
service plan is upgraded.

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

Current production note, last verified on 2026-04-29:

- production domain: `https://app.maxsmartwms.online`
- latest verified deployment for the receiving/putaway feedback fixes:
  `dpl_GywWdFiLKAHEqYgpVmeEzoQXhNPE`
- deployed commit: `31641e1 Improve receiving and putaway exception feedback`
- production bundle seen after deploy: `/assets/index-CaaNQJ-l.js`

When the Vercel app connector cannot inspect deployments, the local CLI fallback
is:

```bash
cd frontend
vercel --prod --scope team_MF0zMZxjrfZ1jRY18fIKHU3P --yes
```

After deploy, confirm that the production HTML references a new bundle and run a
browser smoke against the affected flow:

```bash
curl --fail --silent --show-error https://app.maxsmartwms.online | sed -n '1,20p'
```

## 3. Smoke test after deploy

Check these in order:

1. Backend health endpoint: `GET /health`
2. Frontend loads from Vercel
3. Registration works
4. Login works
5. Dashboard loads
6. Inventory page loads

The backend health response should expose deployment metadata so we can confirm
which backend build is actually live:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "build_sha": "0123456789abcdef0123456789abcdef01234567",
  "branch": "main",
  "service_id": "srv-..."
}
```

If `/health` only returns `status` and `version`, the production backend is
still running an older build and has not picked up the latest code yet.

## 4. Important deployment note

The repo currently contains two different backend deployment stories:

- [`/Volumes/MaxRelocated/WMS/render.yaml`](/Volumes/MaxRelocated/WMS/render.yaml)
  describes a Render service blueprint.
- [`/Volumes/MaxRelocated/WMS/.github/workflows/deploy.yml`](/Volumes/MaxRelocated/WMS/.github/workflows/deploy.yml)
  is a guarded legacy AWS ECS deployment workflow.

The live production backend at [api.maxsmartwms.online](https://api.maxsmartwms.online)
is currently served from Render, not from the GitHub ECS workflow. That means:

- pushes to `main` do not prove the Render service has deployed
- the GitHub deploy workflow is not the source of truth for the live backend
- the legacy AWS ECS workflow requires an explicit `YES` confirmation and
  should not be used for normal production deploys
- `render.yaml` mirrors the current Docker service shape, but the live Render
  dashboard remains the operational source of truth unless the service is
  explicitly synced from the Blueprint

To keep the live backend aligned with `main`, this repo now also includes:

- [`/Volumes/MaxRelocated/WMS/.github/workflows/render-backend-deploy.yml`](/Volumes/MaxRelocated/WMS/.github/workflows/render-backend-deploy.yml)

That workflow no longer depends on a deploy hook. The current production path is
Render auto deploy on `main`; the GitHub workflow waits for
`https://api.maxsmartwms.online/health` to report the pushed Git SHA.

The deploy hook is only an optional future control if Render auto deploy is
disabled or if GitHub Actions needs to become the explicit production gate. The
canonical operational notes live in
[`/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md`](/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md).

Production verification on 2026-04-15 confirmed that the live Render service
already has:

- auto deploy enabled
- branch tracking set to `main`
- commit-triggered deployment active

The canonical way to confirm what is live is still:

- `GET https://api.maxsmartwms.online/health`
- read `build_sha`, `branch`, and `service_id`

## 5. Known limitations for this first deployment

- WebSocket endpoints exist and are better suited to Render than Vercel.
- Survey responses currently write to local disk and should eventually move to object storage or the database.
- PDF generation may need extra Render system package support depending on the exact code path used.
- CORS must include the Vercel frontend URL.
