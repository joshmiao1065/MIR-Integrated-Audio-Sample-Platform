# Deployment & New Feature Guide

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Pre-Deploy Checklist](#2-pre-deploy-checklist)
3. [Deploy Backend → Railway](#3-deploy-backend--railway)
4. [Deploy Frontend → Vercel](#4-deploy-frontend--vercel)
5. [Wire CORS (two-pass)](#5-wire-cors-two-pass)
6. [Run the MIR Worker Locally](#6-run-the-mir-worker-locally)
7. [User Audio Upload Feature](#7-user-audio-upload-feature)
8. [Social Data Seeding](#8-social-data-seeding)
9. [Debugging Reference](#9-debugging-reference)

---

## 1. Architecture Overview

```
Browser  ──►  Vercel (React/Vite, static)
                  │
                  │  /api/*
                  ▼
             Railway (FastAPI, 1 worker)
                  │  CLAP search only
                  │
          ┌───────┴────────┐
          │                │
       Supabase        Google Drive
    (Postgres DB,     (audio files,
     pgvector)         OAuth2 refresh
                        token in .env)

Local machine ──►  process_queue worker
                    (CLAP + YAMNet + MusiCNN)
                    writes results back to Supabase
```

**Why the MIR worker stays local:**  
CLAP (~900 MB), YAMNet, and MusiCNN together need ~3 GB RAM.  Railway Hobby
provides 8 GB, but Railway only needs CLAP for the `/api/search/*` endpoints.
The `process_queue` batch worker connects directly to Supabase over the public
internet and runs fine locally.

---

## 2. Pre-Deploy Checklist

Run these locally before touching Railway or Vercel:

```bash
# Verify the server starts cleanly
cd audio-sample-manager
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Verify the frontend builds without errors
cd frontend
npm run build
```

Confirm every `.env` variable has a value — Railway will error on any missing
required field from `app/config.py`.

---

## 3. Deploy Backend → Railway

### 3.1  Install the Railway CLI

```bash
npm install -g @railway/cli
railway login          # opens browser OAuth
```

### 3.2  Create the Railway project

```bash
# From the audio-sample-manager/ directory (NOT the repo root)
cd audio-sample-manager
railway init           # "Create new project" → give it a name
```

In the Railway dashboard, go to **Settings → General → Root Directory** and set
it to `audio-sample-manager` if it isn't already.

### 3.3  Set environment variables

In the Railway dashboard → your service → **Variables**, add every variable
from your local `.env` file:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Supabase asyncpg connection string |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | anon key |
| `SUPABASE_SERVICE_KEY` | service role key |
| `SUPABASE_STORAGE_BUCKET` | `audio-previews` |
| `FREESOUND_API_KEY` | your key |
| `SECRET_KEY` | JWT signing secret (use `openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` |
| `GDRIVE_FOLDER_ID` | Drive folder ID |
| `GDRIVE_CLIENT_ID` | OAuth2 client ID |
| `GDRIVE_CLIENT_SECRET` | OAuth2 client secret |
| `GDRIVE_REFRESH_TOKEN` | refresh token from `scripts/gdrive_auth.py` |
| `ALLOWED_ORIGINS` | `http://localhost:5173` *(update after Vercel deploy)* |

Do **not** set `ALLOWED_ORIGINS` to the Vercel URL yet — you don't know it
until after the frontend deploy. See §5.

### 3.4  Deploy

```bash
# From audio-sample-manager/
railway up
```

Railway detects Python via `requirements.txt`, then `nixpacks.toml` overrides
the install command to use `requirements-railway.txt` (CPU-only torch, no TF).
The `Procfile` sets the start command.

Build takes **4–8 minutes** on first deploy (downloading CPU torch wheels).
Subsequent deploys are faster (layer caching).

### 3.5  Get the Railway URL

In the dashboard, go to **Settings → Networking → Generate Domain**.  You'll
get a URL like `your-app.railway.app`.  Copy it — you need it for Vercel.

### 3.6  Smoke test Railway

```bash
curl https://your-app.railway.app/health
# → {"status":"ok"}

curl https://your-app.railway.app/api/admin/queue
# → {"counts":{...}, ...}
```

If `/health` returns 502 or times out, check **Railway → Deployments → Logs**
for the startup error.  Common causes:

- Missing env var → `ValidationError` from pydantic-settings at import time
- Google Drive misconfigured → `RuntimeError` from `gdrive._service()` at startup
- Port binding → ensure start command uses `$PORT` (the Procfile already does this)

---

## 4. Deploy Frontend → Vercel

### 4.1  Install Vercel CLI

```bash
npm install -g vercel
vercel login
```

### 4.2  Set the API URL

```bash
# In frontend/
echo "VITE_API_URL=https://your-app.railway.app" > .env.production
```

Or set it as an environment variable in the Vercel dashboard after first deploy.

### 4.3  Deploy

```bash
cd frontend
vercel --prod
```

When prompted:
- **Set up and deploy?** → Yes
- **Which scope?** → your personal account
- **Link to existing project?** → No (first time)
- **Project name?** → `audio-sample-manager` (or anything)
- **In which directory is your code?** → `.` (current directory, `frontend/`)
- **Want to override settings?** → No

Vercel detects Vite automatically and runs `npm run build`.  `vercel.json`
ensures all routes serve `index.html` (SPA routing).

After deploy, Vercel prints a URL like `your-app.vercel.app`.

---

## 5. Wire CORS (two-pass)

Now that you have both the Railway URL and the Vercel URL, update the backend's
allowed origins:

In the Railway dashboard → **Variables**:

```
ALLOWED_ORIGINS=http://localhost:5173,https://your-app.vercel.app
```

Railway auto-redeploys on variable change.  Once it's live, open the Vercel
URL in a browser and confirm the app loads and can list samples.

The `ALLOWED_ORIGINS` variable is comma-separated.  Keep `localhost:5173` so
local development still works against the production API if needed.

---

## 6. Run the MIR Worker Locally

The `process_queue` worker connects to Supabase from your local machine and
processes samples whose `status = 'pending'`.  This includes samples uploaded
by users via the `/api/samples/upload` endpoint.

```bash
# In a terminal you own (NOT a background process)
cd audio-sample-manager
source .venv/bin/activate   # or however you activate your env
python -m scripts.process_queue
```

Check it is running:
```bash
ps aux | grep process_queue | grep -v grep
```

Monitor queue progress:
```bash
curl http://localhost:8000/api/admin/queue   # local
curl https://your-app.railway.app/api/admin/queue  # production
```

The worker must be running for uploaded samples to get BPM, key, tags, and
embeddings.  It can be running locally while users interact with the Railway
deployment — both talk to the same Supabase DB.

---

## 7. User Audio Upload Feature

### What was added

| File | Change |
|---|---|
| `app/routers/samples.py` | `POST /api/samples/upload` endpoint |
| `app/services/gdrive.py` | `upload_audio()` now accepts `mimetype` param |
| `frontend/src/api/samples.ts` | `uploadSample(file, title?)` function |
| `frontend/src/pages/UploadPage.tsx` | Upload page with drag-and-drop |
| `frontend/src/App.tsx` | `/upload` route registered |
| `frontend/src/components/Navbar.tsx` | "Upload" link (visible when logged in) |
| `frontend/src/index.css` | Upload page styles |

### How it works

1. User logs in and clicks **Upload** in the navbar.
2. Drag-and-drop or browse for a file (MP3, WAV, OGG, FLAC, AIFF, M4A, max 50 MB).
3. Optionally enter a title (auto-filled from filename).
4. Click **Upload** — the file goes to Railway, which uploads it to Google Drive.
5. A `Sample` row and a `ProcessingQueue(pending)` row are inserted.
6. FastAPI fires `_run_mir_pipeline` as a `BackgroundTask` (Railway) AND the
   local `process_queue` worker will pick it up — whichever claims the queue
   entry first processes it.
7. The response returns immediately with `is_processed=False`.
8. The upload page shows a success message with a link to the sample detail page.
9. BPM, key, tags, and the waveform appear once the worker finishes (a few minutes).

### API reference

```
POST /api/samples/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

Fields:
  file   (required)  audio file
  title  (optional)  display name; defaults to filename stem

Responses:
  201  SampleOut JSON
  400  Empty file
  413  File too large (> 50 MB)
  415  Unsupported file type
  502  Google Drive upload failed
  503  Google Drive not configured
```

### Debugging uploads

**Drive upload hangs or times out:**
- Check `GDRIVE_*` env vars are set on Railway.
- The refresh token may have expired (unused > 6 months) — re-run `scripts/gdrive_auth.py`.
- Railway logs will show the exception from `gdrive.upload_audio`.

**Sample appears but never gets tags/BPM:**
- The `process_queue` worker isn't running locally.
- Check `GET /api/admin/queue` — if `pending` count is growing, start the worker.
- If `failed` count is growing, check `recent_failures` in that response.

**415 Unsupported file type:**
- The accepted extensions are: `.mp3 .wav .ogg .flac .aiff .m4a`.
- Some browsers send `audio/x-m4a` or `audio/x-wav` content types — the
  endpoint validates by file extension, not content-type, so any valid extension
  is accepted regardless of what the browser claims.

---

## 8. Social Data Seeding

### Prerequisites

```bash
pip install faker
```

`faker` is a dev-only dependency not in `requirements.txt`.

### Running the seeder

```bash
# Default: 10 fake users, random seed 42
python -m scripts.seed_social

# Custom options
python -m scripts.seed_social --users 8 --seed 123

# Preview without writing anything
python -m scripts.seed_social --dry-run

# Remove all seed data (email domain @samplelib.demo)
python -m scripts.seed_social --clear
```

### What gets created

| Table | Quantity |
|---|---|
| `users` | 10 (configurable with `--users`) |
| `ratings` | ~250–350 (each user rates ~35% of sample pool) |
| `comments` | ~80–120 (45% of samples get 1–3 comments) |
| `collections` | 10–20 (1–2 per user) |
| `collection_items` | 80–300 (8–15 samples per collection) |
| `download_history` | 80 events |

All fake accounts use password **`demo1234`** and email format
`seed_<username>@samplelib.demo`.

### Comment quality

Comments are generated by inspecting each sample's actual tags and metadata:

- Sample with a `drum` YAMNet tag → *"love the drum on this"*
- Sample with a `jazz` MusiCNN tag → *"perfect for jazz production"*
- Sample with BPM 128 → *"running this at 128 BPM, fits perfectly"*
- Sample with key C# → *"love the C# on this, very versatile"*
- Fallback → *"this slaps"* / *"certified heat"* / etc.

### Collection themes

Collections are named after the dominant tag in the sample pool:

*Drum Rack Essentials, Low End Theory, Keys Collection, Guitar Textures,
String Sessions, Synth Selects, Vocal Chops, Ambient Textures, Electronic
Experiments, Hip-Hop Fundamentals, Jazz Samples, Percussion Toolkit*

If no tag matches a theme, generic names are used:
*My Sample Pack, Session Starters, The Vault, etc.*

### Idempotency

- Re-running the script with the same `--seed` is safe. It detects existing seed
  users and reuses them rather than inserting duplicates.
- Ratings use `ON CONFLICT DO NOTHING` — duplicate `(user_id, sample_id)` pairs
  are silently skipped.
- Comments always insert (each run adds more comments — call `--clear` first if
  you want a clean slate).

### Clearing seed data

```bash
python -m scripts.seed_social --clear
```

This deletes users whose email ends in `@samplelib.demo`.  Cascades remove:
- Their `ratings` (CASCADE)
- Their `collections` and `collection_items` (CASCADE)

Orphaned side effects (harmless):
- `comments.user_id` becomes NULL (SET NULL) — comments remain, attributed to "Anonymous"
- `download_history.user_id` becomes NULL (SET NULL) — history rows remain

---

## 9. Debugging Reference

### Railway

| Symptom | Where to look | Likely cause |
|---|---|---|
| Build fails | Railway → Deployments → Build logs | Missing package, pip resolver conflict |
| 502 on startup | Railway → Deployments → Deploy logs | Missing env var, GDrive misconfigured |
| Search returns empty | Railway → Deployments → Deploy logs | CLAP weights not downloaded; check `laion_clap` startup log |
| CORS error in browser | Browser console → Network tab | `ALLOWED_ORIGINS` doesn't include the Vercel URL |
| Drive upload 503 | Railway logs | `GDRIVE_REFRESH_TOKEN` not set |

### Vercel

| Symptom | Fix |
|---|---|
| Blank page on `/samples/123` (direct URL) | `vercel.json` rewrite rule is missing or wrong |
| API calls fail (network error) | `VITE_API_URL` not set in Vercel env → app calls `localhost:8000` |
| Old build still serving | `vercel --prod` again; check the deployment was assigned to Production |

### Local worker

```bash
# Check queue state
curl http://localhost:8000/api/admin/queue

# Reset stuck entries (status=processing but worker died)
python -m scripts.process_queue --reset-failed

# Re-process done samples missing tags
python -m scripts.process_queue --requeue-done-missing-tags --once

# Check worker is alive
ps aux | grep process_queue | grep -v grep
```

### CORS quick-fix during testing

If you need to unblock yourself immediately (not for production):

```
ALLOWED_ORIGINS=*
```

Set this in Railway variables, wait for redeploy, then narrow it back to the
real Vercel URL once you've confirmed everything works.
