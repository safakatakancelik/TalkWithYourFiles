import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import type { Agent, Citation, FileItem, Note } from './backend/types';
import { Floor2D } from './Floor2D';

export interface LogEntry {
  who: string;
  text: string;
  citations?: Citation[];
}

export interface Huddle {
  /** A question is being worked on: the orchestrator is at the bucket, from the first event to the answer. */
  active: boolean;
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

/** The 3D floor loads on its own, so three.js stays out of the main bundle. */
const Floor3D = lazy(() => import('./Floor3D'));

/** Whether this browser can draw the 3D floor. Without WebGL the flat floor is shown. */
const hasWebGL = (() => {
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
})();

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

  const { working } = huddle;

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

      {hasWebGL ? (
        <Suspense fallback={<div className="floor" />}>
          <Floor3D agents={agents} files={files} huddle={huddle} litAgent={litAgent} litFile={litFile}
            nameOf={nameOf} onAgent={onAgent} onFile={onFile} onMore={onMore} />
        </Suspense>
      ) : (
        <Floor2D agents={agents} files={files} huddle={huddle} litAgent={litAgent} nameOf={nameOf} onAgent={onAgent} onMore={onMore} />
      )}

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
