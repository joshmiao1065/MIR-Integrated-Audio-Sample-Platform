import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  listCollections,
  createCollection,
  deleteCollection,
  getCollectionSamples,
} from "../api/collections";
import { SampleCard } from "../components/SampleCard";
import type { Collection, CollectionVisibility, Sample } from "../types";

export function CollectionsPage() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [samples, setSamples] = useState<Record<string, Sample[]>>({});
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<CollectionVisibility>("public");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listCollections().then(setCollections);
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const c = await createCollection(name.trim(), description.trim(), visibility);
    setCollections((prev) => [c, ...prev]);
    setName("");
    setDescription("");
    setVisibility("public");
    setCreating(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this collection?")) return;
    await deleteCollection(id);
    setCollections((prev) => prev.filter((c) => c.id !== id));
    if (expanded === id) setExpanded(null);
  };

  const handleExpand = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!samples[id]) {
      const s = await getCollectionSamples(id);
      setSamples((prev) => ({ ...prev, [id]: s }));
    }
  };

  return (
    <div className="page collections-page">
      <div className="collections-header">
        <h1>My Collections</h1>
        <button onClick={() => setCreating((v) => !v)} className="create-btn">
          {creating ? "Cancel" : "+ New collection"}
        </button>
      </div>

      {creating && (
        <form onSubmit={handleCreate} className="create-form">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Collection name"
            required
            autoFocus
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
          />
          <label className="form-label">
            Visibility
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as CollectionVisibility)}
              className="visibility-select"
            >
              <option value="public">Public — anyone can view</option>
              <option value="friends">Friends — mutual followers only</option>
              <option value="private">Private — only me</option>
            </select>
          </label>
          <button type="submit">Create</button>
        </form>
      )}

      {collections.length === 0 && !creating && (
        <p className="empty">No collections yet. Create one to start saving samples.</p>
      )}

      <div className="collection-list">
        {collections.map((c) => (
          <div key={c.id} className="collection-item">
            <div className="collection-row">
              <button onClick={() => handleExpand(c.id)} className="collection-name">
                {expanded === c.id ? "▾" : "▸"} {c.name}
                {c.visibility !== "public" && (
                <span className="private-badge">{c.visibility}</span>
              )}
              </button>
              <button onClick={() => handleDelete(c.id)} className="delete-btn">Delete</button>
            </div>
            {c.description && <p className="collection-desc">{c.description}</p>}

            {expanded === c.id && (
              <div className="collection-samples">
                {samples[c.id] == null ? (
                  <div className="loading">Loading…</div>
                ) : samples[c.id].length === 0 ? (
                  <p className="empty">No samples yet. <Link to="/">Browse</Link> to add some.</p>
                ) : (
                  <div className="sample-grid">
                    {samples[c.id].map((s) => (
                      <SampleCard key={s.id} sample={s} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
