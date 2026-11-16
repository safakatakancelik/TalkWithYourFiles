import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { ORCHESTRATOR } from './backend/types';
import type { Agent, Citation, FileItem, Note } from './backend/types';

export interface LogEntry {
  who: string;
  text: string;
  citations?: Citation[];
}

export interface Huddle {
  members: string[];
  /** Which file each translator has been given for this question: agent id to file id. */
  working: Record<string, string>;
  bubble: { agentId: string; text: string } | null;
  reading: string | null;
  /** Goes up by one on every broadcast, to restart the pulse animation. */
  pulse: number;
  log: LogEntry[];
  /** The verifier while it is in the circle: checking claims, or showing its verdict. */
  verifier: null | { state: 'checking' | 'passed' | 'failed' };
}

/** Up to this many translators are all shown. Above it, idle ones collapse into a group. */
const MAX_SHOWN = 10;
const CENTER_Y = 50;

interface Props {
  agents: Agent[];
  files: FileItem[];
  notes: Note[];
  huddle: Huddle;
  litAgent: string | null;
  litFile: string | null;
  nameOf: (id: string) => string;
  onAgent: (id: string) => void;
  onFile: (id: string) => void;
  onMore: () => void;
  onCite: (c: Citation) => void;
}

export function Stage({ agents, files, notes, huddle, litAgent, litFile, nameOf, onAgent, onFile, onMore, onCite }: Props) {
  const [logOpen, setLogOpen] = useState(true);
  const logEnd = useRef<HTMLDivElement>(null);
  useEffect(() => { logEnd.current?.scrollIntoView({ block: 'nearest' }); }, [huddle.log.length]);

  const { members, working } = huddle;
  const idle = agents.filter((a) => !members.includes(a.id));
  const shown = agents.length > MAX_SHOWN ? idle.slice(0, Math.max(0, MAX_SHOWN - 1 - members.length)) : idle;
  const hidden = idle.length - shown.length;
  const slots = shown.length + (hidden ? 1 : 0);

  // Idle translators stand on two arcs, left and right of the circle. Members stand inside it.
  const idleSpot = (i: number): CSSProperties => {
    const half = Math.ceil(slots / 2);
    const left = i < half;
    const along = left ? (i + 0.5) / half : (i - half + 0.5) / (slots - half);
    const t = ((left ? 215 - 90 * along : 55 - 90 * along) * Math.PI) / 180;
    return { left: `calc(${50 + Math.cos(t) * 38}% + 0px)`, top: `calc(${CENTER_Y - Math.sin(t) * 38}% + 0px)` };
  };
  const spot = (a: Agent): CSSProperties => {
    const j = members.indexOf(a.id);
    if (j < 0) return idleSpot(shown.indexOf(a));
    const t = Math.PI * (1.15 - (1.3 * (j + 0.5)) / members.length);
    return { left: `calc(50% + ${Math.cos(t) * 64}px)`, top: `calc(${CENTER_Y}% + ${-Math.sin(t) * 64}px)` };
  };
  const fileName = (id: string) => files.find((f) => f.id === id)?.name ?? id;
  const active = members.length > 0;

  return (
    <section className="stage">
      {/* Files live on their own shelf. They are never drawn as agents. */}
      <aside className="shelf">
        <header><strong>Files</strong><span className="muted">{files.length}</span></header>
        <div className="tiles">
          {files.length === 0 && <p className="muted">No files yet. Upload some in the explorer (E), or press Run demo.</p>}
          {files.map((f) => {
            const readers = Object.keys(working).filter((a) => working[a] === f.id);
            const count = notes.filter((n) => n.fileId === f.id).length;
            return (
              <button key={f.id} className={`tile ${readers.length ? 'busy' : ''} ${litFile === f.id ? 'lit' : ''}`} onClick={() => onFile(f.id)} title={f.name}>
                <span className="tile-name">{f.name}</span>
                <span className="tile-meta">
                  <span className={`badge t-${f.type}`}>{f.type}</span>
                  <span className="muted">{count} note{count === 1 ? '' : 's'}</span>
                </span>
                {readers.length > 0 && <span className="tile-by">Open with {readers.map(nameOf).join(', ')}</span>}
              </button>
            );
          })}
        </div>
      </aside>

      <div className="floor">
        <div className={`huddle ${active ? 'active' : ''}`} style={{ top: `${CENTER_Y}%` }}>
          {!active && <span>huddle</span>}
        </div>

        {agents.filter((a) => members.includes(a.id) || shown.includes(a)).map((a) => (
          <button key={a.id} style={spot(a)} onClick={() => onAgent(a.id)} title={a.name}
            className={`agent ${members.includes(a.id) ? 'in' : ''} ${litAgent === a.id ? 'lit' : ''}`}>
            {huddle.bubble?.agentId === a.id && <span className="bubble">{huddle.bubble.text}</span>}
            {huddle.reading === a.id && <span className="bubble reading">reading {fileName(working[a.id])}…</span>}
            <span className="figure" />
            <span className="label">{a.name}</span>
            {working[a.id]
              ? <span className="holding" title={fileName(working[a.id])}>{fileName(working[a.id])}</span>
              : <span className="badge">{a.specialty}</span>}
          </button>
        ))}

        {hidden > 0 && (
          <button className="agent more" style={idleSpot(shown.length)} onClick={onMore}>
            <span className="figure" />
            <span className="label">+{hidden} more</span>
          </button>
        )}

        <div className={`agent orchestrator ${active ? 'in' : ''}`}
          style={{ left: '50%', top: `calc(${CENTER_Y}% + ${active ? 70 : 138}px)` }}>
          {huddle.pulse > 0 && <span key={huddle.pulse} className="pulse" />}
          {huddle.bubble?.agentId === ORCHESTRATOR && <span className="bubble side">{huddle.bubble.text}</span>}
          <span className="figure" />
          <span className="label">Orchestrator</span>
        </div>

        <div className={`agent verifier ${huddle.verifier ? 'in' : ''}`} title="Verifier"
          style={{ left: `calc(50% + ${huddle.verifier ? 58 : 112}px)`, top: `calc(${CENTER_Y}% + ${huddle.verifier ? 46 : 138}px)` }}>
          {huddle.verifier && huddle.verifier.state !== 'checking' && (
            <span className={`mark ${huddle.verifier.state}`} aria-label={huddle.verifier.state}>{huddle.verifier.state === 'passed' ? '✓' : '✗'}</span>
          )}
          <span className="figure" />
          <span className="label">Verifier</span>
        </div>
      </div>

      {logOpen ? (
        <aside className="log">
          <header>
            <strong>Huddle log</strong>
            <button onClick={() => setLogOpen(false)} aria-label="Hide the huddle log">Hide</button>
          </header>
          <div className="entries">
            {huddle.log.length === 0 && <p className="muted">The agents' discussion appears here.</p>}
            {huddle.log.map((e, i) =>
              e.who === 'system' ? <p key={i} className="muted">{e.text}</p> : (
                <p key={i}>
                  <b>{nameOf(e.who)}</b> {e.text}{' '}
                  {e.citations?.map((c) => <button key={c.n} className="cite" onClick={() => onCite(c)}>{c.n}</button>)}
                </p>
              ))}
            <div ref={logEnd} />
          </div>
        </aside>
      ) : (
        <button className="log-toggle" onClick={() => setLogOpen(true)}>Huddle log ({huddle.log.length})</button>
      )}
    </section>
  );
}
