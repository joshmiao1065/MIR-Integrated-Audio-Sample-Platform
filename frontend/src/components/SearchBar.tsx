import { useState, useRef } from "react";
import { textSearch, audioSearch } from "../api/samples";
import type { Sample } from "../types";

interface SearchBarProps {
  onResults: (results: Sample[]) => void;
  onLoading: (loading: boolean) => void;
  onError?: (msg: string | null) => void;
}

export function SearchBar({ onResults, onLoading, onError }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"text" | "audio">("text");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleTextSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    onLoading(true);
    onError?.(null);
    try {
      const results = await textSearch(query.trim());
      onResults(results);
    } catch (err: any) {
      const status = err.response?.status;
      const msg =
        status === 502 || status === 503
          ? "Semantic search needs CLAP, which can’t run on the free-tier server (out of memory). Run the backend locally to use text search."
          : `Search failed (${status ?? "network error"}). Please try again.`;
      onError?.(msg);
    } finally {
      onLoading(false);
    }
  };

  const handleAudioSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onLoading(true);
    onError?.(null);
    try {
      const results = await audioSearch(file);
      onResults(results);
    } catch (err: any) {
      const status = err.response?.status;
      const msg =
        status === 502 || status === 503
          ? "Audio search needs CLAP, which can’t run on the free-tier server. Run the backend locally."
          : `Search failed (${status ?? "network error"}). Please try again.`;
      onError?.(msg);
    } finally {
      onLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="search-bar">
      <div className="mode-toggle">
        <button
          className={mode === "text" ? "active" : ""}
          onClick={() => setMode("text")}
        >
          Text
        </button>
        <button
          className={mode === "audio" ? "active" : ""}
          onClick={() => setMode("audio")}
        >
          Audio
        </button>
      </div>

      {mode === "text" ? (
        <form onSubmit={handleTextSearch} className="text-search-form">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. punchy kick drum, ambient pad, lo-fi guitar..."
            className="search-input"
          />
          <button type="submit" className="search-btn">Search</button>
        </form>
      ) : (
        <div className="audio-search">
          <label className="audio-upload-label">
            <span>Drop or select an audio file to find similar sounds</span>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*"
              onChange={handleAudioSearch}
              style={{ display: "none" }}
            />
          </label>
        </div>
      )}
    </div>
  );
}
