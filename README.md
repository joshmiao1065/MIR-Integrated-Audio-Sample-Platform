# Audio Sample Manager

AI-powered audio sample library with automatic BPM detection, key analysis, semantic tagging, and natural language search — built as a Cooper Union ECE464 Databases final project.

## Features

- **Semantic search** — find samples by text description or by uploading a reference audio clip (CLAP embeddings + pgvector)
- **Auto-tagging** — every sample is classified by YAMNet (521 sound-event classes) and MusiCNN (genre/mood/instrumentation)
- **Audio features** — BPM, key, energy, loudness, spectral centroid, ZCR extracted via Librosa
- **Browse & filter** — paginated sample library with tag pills, waveform player, BPM/key chips
- **Social layer** — comments, 1–5 star ratings, download tracking, user collections
- **Bulk ingestion** — scraper pulls samples from Freesound APIv2; overnight pipeline processes the backlog concurrently

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.111 + Uvicorn (fully async) |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL + pgvector (HNSW cosine index) |
| Migrations | Alembic 1.13 (async runner) |
| File storage | Supabase Storage (S3-compatible) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Embeddings | LAION-CLAP — 512-dim audio/text joint embedding |
| Sound events | Google YAMNet (TF Hub, 521 AudioSet classes) |
| Music tags | MTG MusiCNN (MagnaTagATune labels) |
| Audio features | Librosa 0.10 |
| Scraper | Freesound APIv2 (httpx) |
| Frontend | React + Vite + TypeScript |
| Waveform | Wavesurfer.js |
| State | Zustand |

## Project Structure

```
audio-sample-manager/
├── alembic/                  # Migrations (async runner)
├── app/
│   ├── main.py               # FastAPI app, CORS, router registration
│   ├── models/               # SQLAlchemy ORM models (16 tables)
│   ├── routers/              # auth, samples, search, social, collections
│   ├── schemas/              # Pydantic v2 schemas
│   ├── workers/              # CLAP, YAMNet, MusiCNN, Librosa workers + registry
│   └── scraper/              # Freesound API client
├── scripts/
│   ├── ingest_freesound.py   # One-off ingestion CLI
│   ├── ingest_overnight.py   # Bulk ingestion across ~300 queries
│   └── process_queue.py      # Batch MIR worker (polls processing_queue)
└── frontend/                 # React + Vite app
```

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL with the `pgvector` extension
- Node.js 18+
- Supabase project (for file storage)
- Freesound API key

### Environment

Copy `.env.example` to `.env` and fill in all values:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/audio_samples
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=audio-previews
FREESOUND_API_KEY=your-freesound-api-key
SECRET_KEY=generate-a-strong-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Install & migrate

```bash
pip install -r requirements.txt
alembic upgrade head
```

### Run

```bash
# Backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

API docs available at `http://localhost:8000/docs`.
Frontend at `http://localhost:5173`.

## Ingestion & MIR Pipeline

```bash
# Ingest samples from Freesound (queues MIR processing)
python -m scripts.ingest_freesound "kick drum" --limit 200

# Run the MIR worker to process the queue
python -m scripts.process_queue

# Check pipeline progress
curl http://localhost:8000/api/admin/queue
```

The MIR pipeline runs three ML models per sample (CLAP + YAMNet + MusiCNN) in a background task split across three DB sessions to survive PgBouncer connection timeouts. YAMNet and MusiCNN run concurrently; MusiCNN is isolated in a subprocess to prevent TensorFlow eager-mode conflicts.

## API Overview

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/token` | Login, get JWT |
| GET | `/api/samples/` | Browse samples |
| GET | `/api/samples/{id}` | Sample detail |
| POST | `/api/search/text` | Natural language search |
| POST | `/api/search/audio` | Search by reference audio upload |
| POST | `/api/samples/{id}/ratings` | Rate a sample (1–5) |
| POST | `/api/samples/{id}/comments` | Comment on a sample |
| GET | `/api/collections/` | List user collections |
| GET | `/api/admin/queue` | MIR pipeline queue status |

## Database Schema

16 tables across five domains:

- **Core:** `samples`, `audio_embeddings` (512-dim vector), `audio_metadata`
- **Taxonomy:** `tags`, `sample_tags`
- **Collections:** `packs`, `pack_samples`, `collections`, `collection_items`
- **Social:** `comments`, `ratings`, `download_history`
- **System:** `users`, `search_queries`, `processing_queue`, `api_audit_log`

Vector search uses a pgvector HNSW index on `audio_embeddings.embedding` with cosine distance (`vector_cosine_ops`, m=16, ef_construction=64).

## Known Limitations

- CLAP (~900 MB weights) requires significant RAM; not suitable for free-tier cloud without lazy loading
- MusiCNN returns no tags for audio shorter than 3 seconds
- `samples.file_size_bytes` reflects the Freesound original, not the stored MP3 preview
- Supabase free tier storage cap is 1 GB (~4,000–6,000 tracks)
- No audio file upload endpoint — samples must be pre-uploaded to Supabase Storage
