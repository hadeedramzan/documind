import { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API || "http://localhost:8000";

function inline(t) {
  return t.split(/(\*\*[^*]+\*\*|\[\d+\])/g).map((p, i) => {
    if (/^\*\*.+\*\*$/.test(p)) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (/^\[\d+\]$/.test(p)) return <sup key={i} className="cite">{p.slice(1, -1)}</sup>;
    return p;
  });
}

function Rich({ text }) {
  const out = [];
  let list = [];
  const flush = () => { if (list.length) { out.push(<ul key={out.length}>{list}</ul>); list = []; } };
  text.split("\n").forEach((l, i) => {
    const m = l.match(/^\s*[-*]\s+(.*)/);
    if (m) list.push(<li key={i}>{inline(m[1])}</li>);
    else { flush(); if (l.trim()) out.push(<p key={out.length}>{inline(l)}</p>); }
  });
  flush();
  return <>{out}</>;
}

export default function App() {
  const [files, setFiles] = useState([]);
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const endRef = useRef(null);

  const loadFiles = () => fetch(`${API}/files`).then(r => r.json()).then(setFiles).catch(() => {});
  useEffect(() => { loadFiles(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function upload(e) {
    const f = e.target.files[0];
    if (!f) return;
    setStatus(`Indexing ${f.name}...`);
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch(`${API}/upload`, { method: "POST", body: fd });
    const j = await r.json();
    setStatus(r.ok ? `${j.file}: ${j.chunks} chunks indexed` : j.detail);
    e.target.value = "";
    loadFiles();
  }

  async function ask(e) {
    e.preventDefault();
    if (!q.trim() || busy) return;
    const question = q;
    setQ("");
    setBusy(true);
    setMsgs(m => [...m, { role: "user", text: question }]);
    try {
      const r = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const j = await r.json();
      setMsgs(m => [...m, r.ok
        ? { role: "ai", text: j.answer, sources: j.sources }
        : { role: "ai", text: j.detail || "Error" }]);
    } catch {
      setMsgs(m => [...m, { role: "ai", text: "Backend not reachable." }]);
    }
    setBusy(false);
  }

  async function reset() {
    await fetch(`${API}/reset`, { method: "DELETE" });
    setMsgs([]); setStatus(""); loadFiles();
  }

  return (
    <div className="app">
      <aside>
        <h1>DocuMind</h1>
        <label className="btn">
          Upload PDF / TXT / MD
          <input type="file" accept=".pdf,.txt,.md" onChange={upload} hidden />
        </label>
        <p className="status">{status}</p>
        <ul>{files.map(f => <li key={f}>{f}</li>)}</ul>
        {files.length > 0 && <button className="link" onClick={reset}>Clear all</button>}
      </aside>
      <main>
        <div className="chat">
          {msgs.length === 0 && <p className="empty">Upload a document, then ask a question about it.</p>}
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "ai" ? <Rich text={m.text} /> : <p>{m.text}</p>}
              {m.sources && m.sources.length > 0 && (
                <details>
                  <summary>{m.sources.length} source{m.sources.length > 1 ? "s" : ""} cited</summary>
                  {m.sources.map(s => (
                    <blockquote key={s.id}>
                      <b>[{s.id}] {s.source}, p.{s.page}</b><br />{s.snippet}...
                    </blockquote>
                  ))}
                </details>
              )}
            </div>
          ))}
          {busy && <div className="msg ai"><p>Thinking...</p></div>}
          <div ref={endRef} />
        </div>
        <form onSubmit={ask}>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ask about your documents..." />
          <button disabled={busy}>Ask</button>
        </form>
      </main>
    </div>
  );
}
