import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { backend } from './backend';
import type { Agent, Citation, ContextMap, FileItem, Session } from './backend/types';

function Drawer({ title, side, wide, onClose, actions, children }: {
  title: string; side: 'left' | 'right'; wide?: boolean; onClose: () => void; actions?: ReactNode; children: ReactNode;
}) {
  return (
    <aside className={`drawer ${side} ${wide ? 'wide' : ''}`}>
      <header>
        <strong>{title}</strong>
        <span className="grow" />
        {actions}
        <button onClick={onClose} aria-label={`Close ${title}`}>Close</button>
      </header>
      <div className="drawer-body">{children}</div>
    </aside>
  );
}

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
const size = (kb: number) => (kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`);

export function Explorer({ files, agents, onUpload, onAgent, onClose }: {
  files: FileItem[]; agents: Agent[]; onUpload: (files: FileList) => void; onAgent: (id: string) => void; onClose: () => void;
}) {
  const [view, setView] = useState<'files' | 'agents'>('files');
  const input = useRef<HTMLInputElement>(null);
  const agentOf = (fileId: string) => agents.find((a) => a.fileIds.includes(fileId));
  return (
    <Drawer title="Explorer" side="left" onClose={onClose}
      actions={<button className="primary" onClick={() => input.current?.click()}>Upload files</button>}>
      <input ref={input} type="file" multiple hidden
        onChange={(e) => { if (e.target.files?.length) onUpload(e.target.files); e.target.value = ''; }} />
      <div className="tabs">
        <button className={view === 'files' ? 'on' : ''} onClick={() => setView('files')}>By file ({files.length})</button>
        <button className={view === 'agents' ? 'on' : ''} onClick={() => setView('agents')}>By agent ({agents.length})</button>
      </div>
      {files.length === 0 && <p className="muted">No files yet. Uploaded files are only listed here; nothing is sent anywhere.</p>}
      {view === 'files' && files.length > 0 && (
        <table>
          <thead><tr><th>File</th><th>Type</th><th>Size</th><th>Added</th><th>Translator</th></tr></thead>
          <tbody>
            {files.map((f) => {
              const a = agentOf(f.id);
              return (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td><span className={`badge t-${f.type}`}>{f.type}</span></td>
                  <td>{size(f.sizeKb)}</td>
                  <td>{day(f.uploadedAt)}</td>
                  <td>{a ? <button className="link" onClick={() => onAgent(a.id)}>Open</button> : 'None'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {view === 'agents' && agents.length > 0 && (
        <table>
          <thead><tr><th>Translator</th><th>Files</th></tr></thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id}>
                <td><button className="link" onClick={() => onAgent(a.id)}>{a.name}</button></td>
                <td>{a.fileIds.map((id) => files.find((f) => f.id === id)?.name).join(', ') || 'No files'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}

export function Sessions({ sessions, current, onOpen, onNew, onClose }: {
  sessions: Session[]; current: string | null; onOpen: (id: string) => void; onNew: () => void; onClose: () => void;
}) {
  return (
    <Drawer title="Sessions" side="left" onClose={onClose} actions={<button className="primary" onClick={onNew}>New session</button>}>
      {sessions.length === 0 && <p className="muted">No sessions yet. Ask a question to start one.</p>}
      {sessions.length > 0 && (
        <table>
          <thead><tr><th>Session</th><th>Messages</th><th>Last used</th></tr></thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className={s.id === current ? 'current' : ''}>
                <td><button className="link" onClick={() => onOpen(s.id)}>{s.title}</button></td>
                <td>{s.messageCount}</td>
                <td>{day(s.updatedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}

export function ContextMapPanel({ map, onClose }: { map: ContextMap; onClose: () => void }) {
  const [wide, setWide] = useState(false);
  const W = 640, H = 520;
  const ring = (kind: 'file' | 'entity', radius: number, offset: number) => {
    const nodes = map.nodes.filter((n) => n.kind === kind);
    return nodes.map((n, i) => {
      const t = (2 * Math.PI * i) / nodes.length + offset;
      return { ...n, x: W / 2 + Math.cos(t) * radius * 1.15, y: H / 2 + Math.sin(t) * radius };
    });
  };
  const placed = [...ring('entity', 95, 0.4), ...ring('file', 215, 0)];
  const at = (id: string) => placed.find((n) => n.id === id);
  return (
    <Drawer title="Context map" side="left" wide={wide} onClose={onClose}
      actions={<button onClick={() => setWide(!wide)}>{wide ? 'Narrow' : 'Expand'}</button>}>
      {map.nodes.length === 0 ? <p className="muted">The map fills in as you add files and ask questions.</p> : (
        <>
          <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Files and the entities they are linked to">
            {map.links.map((l, i) => {
              const a = at(l.from), b = at(l.to);
              return a && b ? <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} /> : null;
            })}
            {placed.map((n) => (
              <g key={n.id} className={n.kind} transform={`translate(${n.x},${n.y})`}>
                {n.kind === 'file' ? <rect x={-7} y={-9} width={14} height={18} rx={2} /> : <circle r={7} />}
                <text y={24} textAnchor="middle">{n.label}</text>
              </g>
            ))}
          </svg>
          <p className="muted">Squares are files. Circles are entities found in them. {map.nodes.length} nodes, {map.links.length} links.</p>
        </>
      )}
    </Drawer>
  );
}

export function CitationPanel({ citation: c, file, onClose }: { citation: Citation; file?: FileItem; onClose: () => void }) {
  const [before, after] = c.passage.split(c.quote);
  return (
    <Drawer title={`Citation ${c.n}`} side="right" onClose={onClose}>
      <p><strong>{file?.name ?? 'Unknown file'}</strong> {file && <span className={`badge t-${file.type}`}>{file.type}</span>}</p>
      <p className="muted">{c.location}</p>
      <blockquote>{before}<mark>{c.quote}</mark>{after}</blockquote>
      <p className="muted">Supplied by the translator for this file, highlighted on the stage.</p>
    </Drawer>
  );
}

export function AgentCard({ ws, agent, files, onClose }: { ws: string; agent: Agent; files: FileItem[]; onClose: () => void }) {
  const [talk, setTalk] = useState<{ me: boolean; text: string }[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const mine = files.filter((f) => agent.fileIds.includes(f.id));

  const ask = async () => {
    const q = text.trim();
    if (!q || busy) return;
    setText(''); setBusy(true);
    setTalk((t) => [...t, { me: true, text: q }]);
    const reply = await backend.askTranslator(ws, agent.id, q);
    setTalk((t) => [...t, { me: false, text: reply.text }]);
    setBusy(false);
  };

  return (
    <Drawer title="Translator" side="right" onClose={onClose}>
      <p><strong>{agent.name}</strong></p>
      {mine.length === 0 && <p className="muted">This translator has no files.</p>}
      {mine.map((f) => (
        <div key={f.id} className="file-card">
          <span>{f.name}</span> <span className={`badge t-${f.type}`}>{f.type}</span> <span className="muted">{size(f.sizeKb)}</span>
          <p>{f.summary}</p>
        </div>
      ))}
      <div className="mini-chat">
        {talk.length === 0 && <p className="muted">Ask this translator about its file directly.</p>}
        {talk.map((m, i) => <div key={i} className={`msg ${m.me ? 'user' : 'assistant'}`}>{m.text}</div>)}
        {busy && <div className="msg assistant"><span className="status"><i className="dot" />Reading</span></div>}
      </div>
      <form className="input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask this translator" aria-label="Question for this translator" />
        <button className="primary" disabled={busy || !text.trim()}>Ask</button>
      </form>
    </Drawer>
  );
}
