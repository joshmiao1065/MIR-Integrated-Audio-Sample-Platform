# Audio Sample Manager

MIR-powered audio sample discovery platform with semantic search, automatic classification, and a social layer — built as a Cooper Union ECE464 Databases final project.

**Live demo:**
- Frontend — https://audio-sample-manager.vercel.app
- Backend API — https://audio-sample-manager-production.up.railway.app/docs

> **Note on search:** CLAP (~900 MB) can't run on Railway's free tier. Text/audio search is routed to a local machine via ngrok when the demo is live. If search is unavailable, browse and tag-filtering still work from the Railway backend.

---

## Features

### Discovery
- **Semantic text search** — describe what you need in plain English; CLAP turns it into a 512-dim embedding and queries pgvector's HNSW cosine index
- **Audio similarity search** — upload a reference clip to find perceptually similar samples
- **Tag browse** — filter by auto-generated YAMNet or MusiCNN tags, or browse curated genre chips on the home page

### Automatic Classification (MIR Pipeline)
Every sample that enters the system is processed by three ML models running concurrently in a background pipeline:

| Model | Output |
|---|---|
| LAION-CLAP | 512-dim audio/text joint embedding for semantic search |
| Google YAMNet | Top-K sound-event labels from 521 AudioSet classes |
| MTG MusiCNN | Genre/mood/instrumentation tags from MagnaTagATune |
| Librosa | BPM, musical key, RMS energy, loudness (LUFS), spectral centroid, ZCR |

MusiCNN runs in a persistent subprocess to prevent TensorFlow eager-mode conflicts with YAMNet. All three model instances are lazy singletons — weights load exactly once per process.

### Social Layer
- **User profiles** — upload history, activity log, follower/following graph
- **Follow system** — directed follow graph with mutual-follow "friends" semantics for friends-only collections
- **Activity feed** — chronological feed of uploads, comments, ratings, and collection additions from followed users
- **Comments & ratings** — per-sample comment threads and 1–5 star ratings with aggregate stats
- **Collections** — user-curated playlists with `public` / `friends` / `private` visibility
- **Download tracking** — per-sample download counts with authenticated user history

### Recommendations
- **Personalised** — TF-IDF weighted tag scoring over the user's engagement history (ratings, downloads, collection adds); cold-start falls back to weekly trending
- **Similar samples** — tag-overlap ranking against a target sample, returned with `matching_tags` for explainability

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.111 + Uvicorn (fully async) |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL + pgvector extension |
| Vector index | HNSW (cosine, m=16, ef_construction=64) on 512-dim CLAP embeddings |
| Migrations | Alembic 1.13 (async runner) |
| File storage | Google Drive via personal OAuth2 (uses Google One 1 TB quota) |
| Auth | JWT (python-jose, HS256) + bcrypt (passlib) |
| Embeddings | LAION-CLAP 1.1.7 — 512-dim audio/text joint embedding |
| Sound events | Google YAMNet (TF Hub, 521 AudioSet classes) |
| Music tags | MTG MusiCNN 0.1.6 (MagnaTagATune labels, subprocess-isolated) |
| Audio features | Librosa 0.10 |
| Scraper | Freesound APIv2 (httpx) |
| Frontend | React 18 + Vite + TypeScript |
| Waveform | Wavesurfer.js |
| State | Zustand |
| Hosting | Railway (backend) + Vercel (frontend) + Supabase (PostgreSQL) |

---

## Database Schema

16 tables across five domains, all on PostgreSQL + pgvector.

```
Core:        samples, audio_embeddings (512-dim vector), audio_metadata
Taxonomy:    tags, sample_tags
Social:      users, follows, user_activities, comments, ratings, download_history
Collections: packs, pack_samples, collections, collection_items
System:      search_queries, processing_queue, api_audit_log
```

All primary keys are UUID (`uuid_generate_v4()`). All timestamps are `TIMESTAMPTZ`.

Key design choices:
- `audio_embeddings.embedding vector(512)` — HNSW index for sub-millisecond cosine search at scale
- `collections.visibility VARCHAR(20)` — three-value enum (`public` / `friends` / `private`) rather than a boolean; friends-only enforces mutual-follow check
- `user_activities` — push-based activity log (one row per social action) for O(1) feed queries; pull-based UNION across multiple tables was evaluated and rejected for scalability
- `processing_queue` — simple status-machine table (`pending → processing → done/failed`) instead of Celery/Redis; appropriate for a demo-scale project
- Three-session MIR pipeline — DB session is released before ML inference (60–120 s) to survive PgBouncer's ~30 s idle-connection recycling

---

## Project Structure

```
audio-sample-manager/
├── alembic/
│   ├── env.py                    # Async migration runner
│   └── versions/                 # All migrations
├── app/
│   ├── main.py                   # FastAPI app, CORS, router registration
│   ├── config.py                 # Pydantic-settings (.env loader)
│   ├── database.py               # AsyncEngine + AsyncSessionLocal + get_db()
│   ├── deps.py                   # get_current_user / get_optional_user
│   ├── models/                   # SQLAlchemy ORM (16 tables)
│   ├── routers/
│   │   ├── auth.py               # Register + login
│   │   ├── samples.py            # Browse, detail, programmatic create, file upload
│   │   ├── search.py             # Text + audio semantic search
│   │   ├── social.py             # Comments, ratings, downloads, stream
│   │   ├── collections.py        # User collection CRUD + item management
│   │   ├── users.py              # Profiles, follow graph, activity feed
│   │   ├── recommendations.py    # Personalised + similar-sample recommendations
│   │   └── tags.py               # Tag list with usage counts
│   ├── schemas/                  # Pydantic v2 request/response models
│   ├── services/
│   │   └── gdrive.py             # Google Drive upload/delete via OAuth2
│   └── workers/
│       ├── registry.py           # lru_cache singletons: clap(), yamnet(), musicnn()
│       ├── clap_worker.py        # LAION-CLAP encode_text / encode_audio
│       ├── librosa_worker.py     # BPM, key, energy, loudness, spectral features
│       ├── yamnet_worker.py      # YAMNet sound-event classification
│       ├── musicnn_worker.py     # MusiCNN subprocess manager
│       └── _musicnn_proc.py      # Persistent subprocess (stdin/stdout JSON IPC)
├── scripts/
│   ├── gdrive_auth.py            # One-time OAuth2 flow → GDRIVE_REFRESH_TOKEN
│   ├── ingest_freesound.py       # One-off ingestion CLI
│   ├── ingest_overnight.py       # Bulk ingestion across ~300 curated queries
│   ├── process_queue.py          # Batch MIR worker (polls processing_queue)
│   └── seed_social.py            # Seeds demo users, comments, ratings, collections
├── install.sh                    # Full dependency install (handles musicnn --no-deps)
└── frontend/
    └── src/
        ├── api/                  # Axios instances + typed API wrappers
        ├── components/           # Navbar, SearchBar, SampleCard, WavePlayer
        ├── pages/                # Home, Browse, Sample, Upload, Profile, Feed, Collections
        └── store/                # Zustand auth store (JWT in localStorage)
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL with the `pgvector` extension (or a Supabase project)
- Node.js 18+
- Google Cloud project with a Desktop OAuth2 client (for Google Drive file storage)
- Freesound API key

### Environment

Copy `.env.example` to `.env`:

```env
# Database — asyncpg connection string
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Supabase (PostgreSQL host — Storage no longer used for new files)
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=audio-previews

# Google Drive — audio file storage (uses your Google One quota, not a service account)
# Generate once: python -m scripts.gdrive_auth --client-id ID --client-secret SECRET
GDRIVE_FOLDER_ID=your-drive-folder-id
GDRIVE_CLIENT_ID=your-oauth2-client-id.apps.googleusercontent.com
GDRIVE_CLIENT_SECRET=your-oauth2-client-secret
GDRIVE_REFRESH_TOKEN=your-refresh-token

# Freesound
FREESOUND_API_KEY=your-freesound-api-key

# JWT
SECRET_KEY=generate-a-strong-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Install & migrate

```bash
# musicnn must be installed with --no-deps due to a numpy version pin conflict
# Use install.sh rather than bare pip install -r requirements.txt
bash install.sh

alembic upgrade head
```

### Run

```bash
# Backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

- API docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

---

## Authentication

The login form takes your **email address** (not username). The OAuth2 token endpoint looks up users by email:

```
POST /api/auth/register   { email, username, password }
POST /api/auth/token      form: username=<email>, password=<password>
```

Include `Authorization: Bearer <token>` on protected endpoints.

---

## Ingestion & MIR Pipeline

```bash
# Ingest from Freesound (queues MIR for later)
python -m scripts.ingest_freesound "kick drum" --limit 200

# Process the queue (run in a terminal you own — never nohup)
python -m scripts.process_queue

# Reset failed entries and retry
python -m scripts.process_queue --reset-failed --once

# Monitor progress
curl http://localhost:8000/api/admin/queue
```

The pipeline runs three ML models per sample concurrently (YAMNet + MusiCNN via `asyncio.gather`) across three separate DB sessions to survive PgBouncer's idle-connection recycling. CLAP runs sequentially before them.

**Always run `process_queue` in a terminal you own.** If it dies as a background/nohup process, samples accumulate in `pending` indefinitely with no indication.

---

## API Overview

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | Create account |
| POST | `/api/auth/token` | — | Login → JWT (use email as `username` field) |
| GET | `/api/samples/` | — | Browse samples (paginated) |
| POST | `/api/samples/upload` | required | Upload audio file (MP3/WAV/OGG/FLAC, max 50 MB) |
| POST | `/api/search/text` | — | Natural language search (CLAP + pgvector) |
| POST | `/api/search/audio` | — | Search by reference audio upload |
| GET | `/api/users/{username}` | — | User profile |
| POST | `/api/users/{username}/follow` | required | Follow a user |
| GET | `/api/users/feed` | required | Activity feed from followed users |
| GET | `/api/recommendations/` | optional | Personalised recommendations |
| GET | `/api/recommendations/similar/{id}` | — | Similar samples by tag overlap |
| GET | `/api/tags/` | — | All tags with usage counts |
| POST | `/api/samples/{id}/ratings` | required | Rate a sample (1–5 stars) |
| POST | `/api/samples/{id}/comments` | required | Comment on a sample |
| GET | `/api/collections/` | required | List user collections |
| GET | `/api/admin/queue` | — | MIR pipeline queue status |

Full interactive docs at `/docs` (Swagger UI).

---

## Deployment

The project uses a hybrid architecture because CLAP (~900 MB) exceeds Railway's free-tier memory limit (512 MB):

| Component | Host | Notes |
|---|---|---|
| Backend (browse/auth/social/upload) | Railway | `uvicorn app.main:app --workers 1` |
| Search (text + audio) | Local machine → ngrok | CLAP runs locally; tunnel exposes it |
| Frontend | Vercel | Static Vite build |
| Database | Supabase | PostgreSQL + pgvector; free tier pauses after 7 days idle |
| Audio files | Google Drive | Personal OAuth2; uses Google One quota |

The frontend uses two Axios instances (`VITE_API_URL` for Railway, `VITE_SEARCH_URL` for ngrok). Both are baked into the Vite bundle at build time from `frontend/.env.production`. A `localStorage` override (`localStorage.setItem("search_api_url", "...")`) is also supported without a rebuild.

**After each ngrok restart** (URL changes on free tier): update `VITE_SEARCH_URL` in `frontend/.env.production` and run `vercel --prod`.

**If Supabase shows 500 errors:** the project is likely paused. Resume it at https://supabase.com/dashboard and wait ~60 seconds.

---

## Known Limitations

- CLAP (~900 MB) can't run on Railway free tier — search is routed through a local ngrok tunnel
- MusiCNN returns no tags for audio shorter than 3 seconds (analysis window limitation)
- `samples.file_size_bytes` stores the Freesound original file size, not the stored MP3 preview (~150–300 KB each)
- `processing_queue.updated_at` has no auto-update trigger — set manually in code on status changes
- Supabase free tier pauses projects after ~7 days of inactivity; resume from the dashboard before any demo
- MIR processing for user-uploaded files runs on the local worker, not Railway — BPM, key, tags, and embedding appear with a delay after upload
