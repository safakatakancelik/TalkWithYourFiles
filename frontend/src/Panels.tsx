import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { backend } from './backend';
import { WEIGHTS } from './backend/types';
import type { Agent, Citation, ContextMap, FileItem, Note, Session, Weight } from './backend/types';

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
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

export interface NoteActions {
  nameOf: (id: string) => string;
  fileName: (id: string) => string;
  onWeight: (noteIds: string[], weight: Weight) => void;
  onCite: (c: Citation) => void;
}

/** Notes are the only link between files and agents. `by` picks which side of that link to label each note with. */
function NoteList({ notes, by, nameOf, fileName, onWeight, onCite }: NoteActions & { notes: Note[]; by: 'author' | 'file' }) {
  return (
    <>
      {notes.map((n) => (
        <div key={n.id} className={`note ${n.weight === 'off' ? 'off' : ''}`}>
          <div className="note-head">
            <strong>{by === 'author' ? nameOf(n.authorId) : fileName(n.fileId)}</strong>
            <span className="muted">{n.kind}, {day(n.createdAt)}</span>
            <span className="grow" />
            <select value={n.weight} onChange={(e) => onWeight([n.id], e.target.value as Weight)} aria-label="Weight of this note">
              {WEIGHTS.map((w) => <option key={w}>{w}</option>)}
            </select>
          </div>
          <p>
            {n.text}{' '}
            {n.citations.map((c) => <button key={c.n} className="cite" title={c.location} onClick={() => onCite(c)}>{c.n}</button>)}
          </p>
        </div>
      ))}
    </>
  );
}

export function Explorer({ files, notes, onUpload, onFile, onClose }: {
  files: FileItem[]; notes: Note[]; onUpload: (files: FileList) => void; onFile: (id: string) => void; onClose: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <Drawer title="Files" side="left" onClose={onClose}
      actions={<button className="primary" onClick={() => input.current?.click()}>Upload files</button>}>
      <input ref={input} type="file" multiple hidden
        onChange={(e) => { if (e.target.files?.length) onUpload(e.target.files); e.target.value = ''; }} />
      <p className="muted">Files are kept exactly as uploaded and belong to no agent. Agents add notes about them.</p>
      {files.length > 0 && (
        <table>
          <thead><tr><th>File</th><th>Type</th><th>Size</th><th>Added</th><th>Notes</th></tr></thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.id}>
                <td><button className="link" onClick={() => onFile(f.id)}>{f.name}</button></td>
                <td><span className={`badge t-${f.type}`}>{f.type}</span></td>
                <td>{size(f.sizeKb)}</td>
                <td>{day(f.uploadedAt)}</td>
                <td>{notes.filter((n) => n.fileId === f.id).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}

export function AgentsPanel({ agents, notes, onAgent, onCreate, onClose }: {
  agents: Agent[]; notes: Note[]; onAgent: (id: string) => void; onCreate: (name: string, specialty: string) => void; onClose: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [specialty, setSpecialty] = useState('');
  const create = () => {
    if (!name.trim()) return;
    onCreate(name.trim(), specialty.trim().toLowerCase() || 'generic');
    setName(''); setSpecialty(''); setAdding(false);
  };
  return (
    <Drawer title="Agents" side="left" onClose={onClose}
      actions={<button className="primary" onClick={() => setAdding(!adding)}>New agent</button>}>
      <p className="muted">The translator pool for this workspace. The orchestrator picks from it and gives translators files per question.</p>
      {adding && (
        <form className="input new-agent" onSubmit={(e) => { e.preventDefault(); create(); }}>
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, for example Legal translator" aria-label="Agent name" />
          <input value={specialty} onChange={(e) => setSpecialty(e.target.value)} placeholder="Speciality (empty for generic)" aria-label="Speciality" />
          <button className="primary" disabled={!name.trim()}>Create</button>
        </form>
      )}
      <table>
        <thead><tr><th>Translator</th><th>Kind</th><th>Notes</th><th>Files worked on</th></tr></thead>
        <tbody>
          {agents.map((a) => {
            const mine = notes.filter((n) => n.authorId === a.id);
            return (
              <tr key={a.id}>
                <td><button className="link" onClick={() => onAgent(a.id)}>{a.name}</button></td>
                <td><span className="badge">{a.specialty}</span></td>
                <td>{mine.length}</td>
                <td>{new Set(mine.map((n) => n.fileId)).size}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
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

export function CitationPanel({ citation: c, file, foundBy, onClose }: { citation: Citation; file?: FileItem; foundBy: string; onClose: () => void }) {
  const [before, after] = c.passage.split(c.quote);
  return (
    <Drawer title={`Citation ${c.n}`} side="right" onClose={onClose}>
      <p><strong>{file?.name ?? 'Unknown file'}</strong> {file && <span className={`badge t-${file.type}`}>{file.type}</span>}</p>
      <p className="muted">{c.location}</p>
      <blockquote>{before}<mark>{c.quote}</mark>{after}</blockquote>
      <p className="muted">Found by {foundBy}. The file and the agent are highlighted on the stage.</p>
    </Drawer>
  );
}

export function FileCard({ file, notes, actions, onAddNote, onClose }: {
  file: FileItem; notes: Note[]; actions: NoteActions; onAddNote: (text: string) => void; onClose: () => void;
}) {
  const [text, setText] = useState('');
  const about = notes.filter((n) => n.fileId === file.id);
  return (
    <Drawer title="File" side="right" onClose={onClose}>
      <p><strong>{file.name}</strong> <span className={`badge t-${file.type}`}>{file.type}</span></p>
      <p className="muted">{size(file.sizeKb)}, added {day(file.uploadedAt)}. Stored as uploaded.</p>
      <h4>Notes about this file ({about.length})</h4>
      {about.length === 0 && <p className="muted">No agent has worked on this file yet.</p>}
      <NoteList notes={about} by="author" {...actions} />
      <form className="input" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { onAddNote(text.trim()); setText(''); } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add your own note about this file" aria-label="Your note about this file" />
        <button className="primary" disabled={!text.trim()}>Add note</button>
      </form>
    </Drawer>
  );
}

export function AgentCard({ ws, agent, notes, actions, onClose }: { ws: string; agent: Agent; notes: Note[]; actions: NoteActions; onClose: () => void }) {
  const [talk, setTalk] = useState<{ me: boolean; text: string }[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const mine = notes.filter((n) => n.authorId === agent.id);

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
      <p><strong>{agent.name}</strong> <span className="badge">{agent.specialty}</span></p>
      <p className="muted">{plural(mine.length, 'note')} on {plural(new Set(mine.map((n) => n.fileId)).size, 'file')}. It owns no files.</p>
      {mine.length > 0 && (
        <p className="note-head">
          <span>Set all of this agent's notes to</span>
          <select value="" onChange={(e) => e.target.value && actions.onWeight(mine.map((n) => n.id), e.target.value as Weight)} aria-label="Weight for all of this agent's notes">
            <option value="">choose</option>
            {WEIGHTS.map((w) => <option key={w}>{w}</option>)}
          </select>
        </p>
      )}
      <NoteList notes={mine} by="file" {...actions} />
      <div className="mini-chat">
        {talk.length === 0 && <p className="muted">Ask this translator directly.</p>}
        {talk.map((m, i) => <div key={i} className={`msg ${m.me ? 'user' : 'assistant'}`}>{m.text}</div>)}
        {busy && <div className="msg assistant"><span className="status"><i className="dot" />Thinking</span></div>}
      </div>
      <form className="input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask this translator" aria-label="Question for this translator" />
        <button className="primary" disabled={busy || !text.trim()}>Ask</button>
      </form>
    </Drawer>
  );
}
