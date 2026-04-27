import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { uploadSample } from "../api/samples";
import { useAuthStore } from "../store/authStore";
import type { Sample } from "../types";

const ACCEPTED_EXTENSIONS = [".mp3", ".wav", ".ogg", ".flac", ".aiff", ".m4a"];
const MAX_MB = 50;

function stemOf(filename: string): string {
  return filename.replace(/\.[^.]+$/, "");
}

export function UploadPage() {
  const { token } = useAuthStore();
  const navigate = useNavigate();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [uploaded, setUploaded] = useState<Sample | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) navigate("/login");
  }, [token, navigate]);

  function handleFile(f: File) {
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(`Unsupported format "${ext}". Use: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File too large (max ${MAX_MB} MB)`);
      return;
    }
    setFile(f);
    setError("");
    if (!title) setTitle(stemOf(f.name));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const sample = await uploadSample(file, title.trim() || undefined);
      setUploaded(sample);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  function resetForm() {
    setFile(null);
    setTitle("");
    setError("");
    setUploaded(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  if (uploaded) {
    return (
      <div className="page auth-page">
        <div className="auth-card upload-card">
          <h1>Uploaded!</h1>
          <p className="upload-success-msg">
            <strong>{uploaded.title}</strong> is on Google Drive. Tags, BPM, and key
            are generating in the background — check back in a few minutes.
          </p>
          <Link to={`/samples/${uploaded.id}`} className="submit-btn upload-view-btn">
            View sample →
          </Link>
          <button className="upload-again-btn" onClick={resetForm}>
            Upload another
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page auth-page">
      <div className="auth-card upload-card">
        <h1>Upload Sample</h1>

        <form onSubmit={handleSubmit}>
          {/* Drop zone */}
          <div
            className={`upload-drop-zone${dragging ? " dragging" : ""}${file ? " has-file" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const f = e.dataTransfer.files[0];
              if (f) handleFile(f);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(",")}
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
            {file ? (
              <>
                <span className="upload-filename">{file.name}</span>
                <span className="upload-filesize">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </span>
              </>
            ) : (
              <>
                <span className="upload-icon">♪</span>
                <span>Drop an audio file here, or click to browse</span>
                <span className="upload-hint">
                  {ACCEPTED_EXTENSIONS.join("  ")} · max {MAX_MB} MB
                </span>
              </>
            )}
          </div>

          {/* Title */}
          <label htmlFor="upload-title">Title <span className="upload-optional">(optional)</span></label>
          <input
            id="upload-title"
            type="text"
            value={title}
            maxLength={255}
            placeholder="Auto-filled from filename"
            onChange={(e) => setTitle(e.target.value)}
          />

          {error && <p className="error-msg">{error}</p>}

          <button
            type="submit"
            className="submit-btn"
            disabled={!file || uploading}
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </form>
      </div>
    </div>
  );
}
