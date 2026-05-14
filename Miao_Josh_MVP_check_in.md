# ECE 464 – Final Project MVP Check-in
**Josh Miao**

---

## 1. Abstract

I am building an AI-powered audio sample library for music producers. Users can browse a catalogue of ~4,000 samples scraped from Freesound, search by natural language description ("dark cinematic piano") or by uploading a reference audio clip, and interact through ratings, comments, and personal collections. The backend automatically extracts BPM, key, energy, and semantic tags for every sample using a three-model ML pipeline running in the background.

---

## 2. Current State of the Application

The following features are fully operational:

- **Database deployed and accessible** — PostgreSQL + pgvector hosted on Supabase; all 16 tables live, Alembic migrations applied.
- **User authentication** — JWT (HS256) + bcrypt register/login; `Authorization: Bearer` guards protect write endpoints.
- **Core CRUD** — `GET /api/samples/` (paginated browse), `GET /api/samples/{id}` (detail with metadata + tags), `POST /api/samples/` (create + queue MIR pipeline).
- **Social layer** — comments (post/delete own), ratings (1–5, upsert), download tracking with redirect, collection CRUD and item management. I manually created a few users which have commented, rated, and added tracks to collections which all seem to work.
- **Semantic search** — `POST /api/search/text` and `/api/search/audio` use LAION-CLAP embeddings stored in a pgvector HNSW index; cosine distance ranking works end-to-end.
- **MIR background pipeline** — CLAP (512-dim embedding), YAMNet (521 AudioSet classes), MusiCNN (MagnaTagATune tags), and Librosa (BPM, key, energy) all run per sample; ~491 samples fully processed so far.
- **Frontend** — React + Vite app with waveform player (Wavesurfer.js), tag pills, BPM/key chips, audio search upload, ratings UI, and collections management; communicates with the FastAPI backend via Axios.
- **Bulk ingestion** — 4,000 samples scraped from Freesound APIv2 with a concurrent batch pipeline (`scripts/process_queue.py`).

---

## 3. Schema & Architecture Check-in

**16 tables** implemented via Alembic async migrations:

| Domain | Tables |
|---|---|
| Core | `samples`, `audio_embeddings` (512-dim vector), `audio_metadata` |
| Taxonomy | `tags`, `sample_tags` |
| Collections | `packs`, `pack_samples`, `collections`, `collection_items` |
| Social | `comments`, `ratings`, `download_history` |
| System | `users`, `search_queries`, `processing_queue`, `api_audit_log` |

The main indexing decision was a **pgvector HNSW index** on `audio_embeddings.embedding` using cosine distance (`vector_cosine_ops`, m=16, ef\_construction=64). This makes nearest-neighbour search sub-millisecond even at thousands of embeddings. One relational issue encountered: `processing_queue.updated_at` has no PostgreSQL auto-update trigger — it is set manually in code on every status change, which is fragile but functional for the demo scope.

---

## 4. The Pivot

**File storage: Supabase Storage → Google Drive (personal OAuth2).** Supabase's free tier provides 1 GB of object storage. At ~200 KB per MP3 preview, that caps the library at ~5,000 samples — barely enough for a meaningful dataset. I migrated to personal Google Drive (Google One, 1 TB quota) via OAuth2 refresh token. The backend now uses a `gdrive.py` service for upload/delete; `file_url` stores a direct Drive download link. The tradeoff is that Drive URLs redirect through `drive.usercontent.google.com`, requiring `follow_redirects=True` in `httpx` during pipeline download.

**MusiCNN subprocess isolation.** The original plan was to call all three ML models directly in the background task. MusiCNN (`musicnn`) calls `tf.compat.v1.disable_eager_execution()` at import time, which silently breaks YAMNet (a TF2 SavedModel requiring eager tensors). The fix was running MusiCNN in an isolated subprocess — originally via `ProcessPoolExecutor(spawn)`, but this caused a deeper issue: Anaconda's `libprotobuf.so.25.3.0` (injected into the dynamic linker path by the Anaconda Python interpreter) has a different internal struct layout than the build TF 2.20 was compiled against, producing a deterministic segfault inside `sess.run()`. The fix was replacing the executor with a **persistent `/usr/bin/python3` subprocess** (which does not inherit Anaconda's library path) communicating over stdin/stdout JSON IPC. TF loads once at subprocess start; subsequent calls are fast.

---

## 5. Blockers & Next Steps

**Cloud deployment — CLAP memory vs. Railway free tier.** CLAP's weights are ~900 MB. Railway's free tier allows 512 MB per service; the Starter plan ($5/mo) allows 8 GB. The search endpoints (`/api/search/text`, `/api/search/audio`) call `registry.clap()` synchronously before hitting pgvector, so if CLAP cannot load on Railway, search is entirely broken in production. Options are to pay for the Starter plan, implement lazy loading (load CLAP only on first search request and hope Railway does not evict it between requests), or disable search on the deployed backend and run it locally only. None of these is clean.

**Secret management for Google Drive OAuth2.** `GDRIVE_REFRESH_TOKEN` and `GDRIVE_CLIENT_SECRET` live in a local `.env` file. On Railway, these must be set as environment variables. There is currently no automated re-auth flow — if the token is ever revoked (e.g., the OAuth consent screen is modified), a human must re-run `python -m scripts.gdrive_auth` and paste the new token into Railway's dashboard manually. This is fragile for a production-grade deployment.

**No user-facing audio upload.** `POST /api/samples/` accepts a `file_url` that must already exist in Google Drive — there is no endpoint to upload an audio file directly. All content must come through the Freesound scraper. This means the app cannot function as a true personal sample manager where a producer drops in their own files. Adding a multipart upload endpoint that handles Drive upload, queue insertion, and MIR pipeline dispatch in one request would close this gap but is a non-trivial addition.

**Social tables are sparsely populated.** `comments`, `ratings`, `collections`, and `collection_items` only have a few manual entries. A seed script is needed to create a few demo users and populate plausible comments, ratings, and named collections across a sample of tracks before the presentation. I need to create many accounts which require emails to register. I can probably just fake email addresses for the purposes of this project.

**Immediate next steps:** resolve CLAP memory for Railway deployment, deploy backend + frontend, update CORS origins and `VITE_API_URL`, seed social demo data, and prepare the 10-minute live demo script.

---

## 6. Code Access

**GitHub:** [https://github.com/joshmiao1065/MIR-Integrated-Audio-Sample-Platform](https://github.com/joshmiao1065/MIR-Integrated-Audio-Sample-Platform) (public)

Key files: `alembic/versions/001_initial_schema.py` (full schema), `app/routers/samples.py` (`_run_mir_pipeline`), `app/workers/` (CLAP / YAMNet / MusiCNN workers), `scripts/process_queue.py` (batch worker).
