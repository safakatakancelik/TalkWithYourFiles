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
  /** Who is doing something right now, and what, in a few words: agent id (or ORCHESTRATOR, VERIFIER) to activity. */
  busy: Record<string, string>;
  /** What is happening, in one line, and since when (ms since the epoch). Null between questions. */
  now: { text: string; since: number } | null;
  /** Messages between agents, newest last; `from` and `to` are agent ids. Each is drawn once, when it appears. */
  flights: { id: number; from: string; to: string }[];
}

/** The 3D floor loads on its own, so three.js stays out of the main bundle. */
const Floor3D = lazy(() => import('./Floor3D'));

/** Whether this browser can draw the 3D floor. Without WebGL the flat floor is shown. */
export const hasWebGL = (() => {
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
  /** The immersive view covers the stage: the 3D floor stops drawing. */
  paused?: boolean;
}

/** Every entry of the huddle log, scrolled to the newest. Shown beside the stage and on the immersive view's log board. */
export function LogEntries({ log, nameOf, onCite }: { log: LogEntry[]; nameOf: (id: string) => string; onCite: (c: Citation) => void }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [log.length]);
  return (
    <div className="entries">
      {log.length === 0 && <p className="muted">The agents' discussion appears here.</p>}
      {log.map((e, i) =>
        e.who === 'system' ? <p key={i} className="muted">{e.text}</p> : (
          <p key={i}>
            <b>{nameOf(e.who)}</b> {e.text}{' '}
            {e.citations?.map((c) => <button key={c.n} className="cite" onClick={() => onCite(c)}>{c.n}</button>)}
          </p>
        ))}
      <div ref={end} />
    </div>
  );
}

export function Stage({ agents, files, notes, huddle, litAgent, litFile, nameOf, onAgent, onFile, onMore, onCite, paused }: Props) {
  const [logOpen, setLogOpen] = useState(true);

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

      {/* The slot keeps the floor's place when the floor grows to the whole screen on the way into the immersive view. */}
      <div className="floor-slot">
        {hasWebGL ? (
          <Suspense fallback={<div className="floor" />}>
            <Floor3D agents={agents} files={files} huddle={huddle} litAgent={litAgent} litFile={litFile}
              nameOf={nameOf} onAgent={onAgent} onFile={onFile} onMore={onMore} paused={paused} />
          </Suspense>
        ) : (
          <Floor2D agents={agents} files={files} huddle={huddle} litAgent={litAgent} nameOf={nameOf} onAgent={onAgent} onMore={onMore} />
        )}
      </div>

      {logOpen ? (
        <aside className="log">
          <header>
            <strong>Huddle log</strong>
            <button onClick={() => setLogOpen(false)} aria-label="Hide the huddle log">Hide</button>
          </header>
          <LogEntries log={huddle.log} nameOf={nameOf} onCite={onCite} />
        </aside>
      ) : (
        <button className="log-toggle" onClick={() => setLogOpen(true)}>Huddle log ({huddle.log.length})</button>
      )}
    </section>
  );
}
