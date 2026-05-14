import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { listSamples } from "../api/samples";
import { SearchBar } from "../components/SearchBar";
import { SampleCard } from "../components/SampleCard";
import type { Sample } from "../types";

const LIMIT = 20;

const SORT_LABELS: Record<string, string> = {
  new: "New Releases",
  trending: "Trending This Week",
  top_rated: "Top Rated",
};

export function BrowsePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sortParam = (searchParams.get("sort") ?? "new") as "new" | "trending" | "top_rated";
  const tagParam = searchParams.get("tag_name") ?? undefined;

  const [samples, setSamples] = useState<Sample[]>([]);
  const [loading, setLoading] = useState(true);
  const [searched, setSearched] = useState(false);
  const [offset, setOffset] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    if (searched) return;
    setLoading(true);
    listSamples({ sort: sortParam, tag_name: tagParam, limit: LIMIT, offset })
      .then(setSamples)
      .finally(() => setLoading(false));
  }, [offset, searched, sortParam, tagParam]);

  const handleResults = (results: Sample[]) => {
    setSamples(results);
    setSearched(true);
    setOffset(0);
  };

  const clearSearch = () => {
    setSearched(false);
    setOffset(0);
    setSearchError(null);
  };

  const pageTitle = tagParam
    ? `Tag: ${tagParam}`
    : (SORT_LABELS[sortParam] ?? "Browse");

  return (
    <div className="page browse-page">
      <h1 className="browse-title">{pageTitle}</h1>

      <SearchBar onResults={handleResults} onLoading={setLoading} onError={setSearchError} />

      {searchError && (
        <div className="search-error">
          <span>{searchError}</span>
          <button onClick={() => setSearchError(null)} className="clear-btn">✕</button>
        </div>
      )}

      {searched && (
        <div className="search-status">
          <span>{samples.length} result{samples.length !== 1 ? "s" : ""}</span>
          <button onClick={clearSearch} className="clear-btn">Clear search</button>
        </div>
      )}

      {!searched && (
        <div className="sort-tabs">
          {(["new", "trending", "top_rated"] as const).map((s) => (
            <button
              key={s}
              className={`sort-tab ${sortParam === s && !tagParam ? "active" : ""}`}
              onClick={() => { setSearchParams({ sort: s }); setOffset(0); setSamples([]); setLoading(true); }}
            >
              {SORT_LABELS[s]}
            </button>
          ))}
          {tagParam && (
            <button className="sort-tab active">#{tagParam}</button>
          )}
        </div>
      )}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : samples.length === 0 ? (
        <div className="empty">No samples found.</div>
      ) : (
        <div className="sample-grid">
          {samples.map((s) => <SampleCard key={s.id} sample={s} />)}
        </div>
      )}

      {!searched && (
        <div className="pagination">
          <button
            onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            disabled={offset === 0}
          >
            Previous
          </button>
          <button
            onClick={() => setOffset(offset + LIMIT)}
            disabled={samples.length < LIMIT}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
