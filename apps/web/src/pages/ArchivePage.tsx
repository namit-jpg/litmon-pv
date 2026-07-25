import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ArticleListItem } from "../api";

export default function ArchivePage() {
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);

  async function load(search?: string) {
    setLoading(true);
    setError("");
    try {
      const list = await api.articles({
        include_archive: true,
        open_only: false,
        q: search ?? q,
      });
      setItems(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    await load(q);
  }

  async function recall(id: number) {
    setMsg("");
    try {
      await api.recall(id, "Recalled from archive for re-review");
      setMsg(`Article #${id} recalled to review queue.`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Archive</h1>
          <p className="muted">
            Auto-cleared and disposed articles — searchable and recallable (no
            silent discard).
          </p>
        </div>
      </div>

      <form className="row-actions wrap" onSubmit={onSearch}>
        <input
          style={{ minWidth: 260 }}
          placeholder="Search title, PMID, abstract…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button className="btn primary" type="submit">
          Search
        </button>
        <button className="btn" type="button" onClick={() => load("")}>
          Clear
        </button>
      </form>

      {msg && <div className="ok-banner">{msg}</div>}
      {error && <div className="error">{error}</div>}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>No archived articles yet.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Score</th>
              <th>PMID</th>
              <th>Title</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>
                  <span className="pill">{a.status}</span>
                </td>
                <td>{a.composite != null ? a.composite.toFixed(2) : "—"}</td>
                <td>{a.pmid}</td>
                <td>
                  <Link to={`/articles/${a.id}`}>{a.title}</Link>
                </td>
                <td>
                  <button className="btn" onClick={() => recall(a.id)}>
                    Recall
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
