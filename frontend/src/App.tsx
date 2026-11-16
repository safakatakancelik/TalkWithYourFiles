import { useEffect, useRef, useState } from 'react';
import { backend } from './backend';
import { ORCHESTRATOR, VERIFIER } from './backend/types';
import type { Agent, AgentEvent, ChatMsg, Citation, ContextMap, FileItem, Note, Session, Weight, Workspace } from './backend/types';
import { Chat } from './Chat';
import type { ChatMode } from './Chat';
import { AgentCard, AgentsPanel, CitationPanel, ContextMapPanel, Explorer, FileCard, Sessions } from './Panels';
import type { NoteActions } from './Panels';
import { Stage } from './Stage';
import type { Huddle } from './Stage';
// Demo-only imports: the "Run demo" button and its controls drive the mock's clock.
import { clock, resetDemo } from './backend/mock';
import { DEMO_QUESTION, DEMO_WORKSPACE } from './demo/scenario';

const emptyHuddle: Huddle = { members: [], working: {}, bubble: null, reading: null, pulse: 0, log: [], verifier: null };
/** The backend's default TWYF_MAX_VERIFY_ROUNDS. The events do not carry it. */
const MAX_ROUNDS = 3;
const MODES: ChatMode[] = ['bar', 'half', 'full'];
const SPEEDS = [0.5, 1, 2, 4];
let counter = 0;
const uid = () => `m-${counter++}`;

export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [ws, setWs] = useState(''); // the first workspace the backend lists
  const [files, setFiles] = useState<FileItem[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [map, setMap] = useState<ContextMap>({ nodes: [], links: [] });
  const [sid, setSid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Record<string, ChatMsg[]>>({});
  const [huddle, setHuddle] = useState<Huddle>(emptyHuddle);
  const [mode, setMode] = useState<ChatMode>('half');
  const [panel, setPanel] = useState<null | 'E' | 'A' | 'S' | 'C'>(null);
  const [cite, setCite] = useState<Citation | null>(null);
  // The file or the agent whose card is open. They are separate things with separate cards.
  const [card, setCard] = useState<{ kind: 'file' | 'agent'; id: string } | null>(null);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [theme, setTheme] = useState(() => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  const ctrl = useRef<AbortController | null>(null);
  const names = useRef<Record<string, string>>({});
  const fileNames = useRef<Record<string, string>>({});

  const nameOf = (id: string) =>
    id === ORCHESTRATOR ? 'Orchestrator' : id === VERIFIER ? 'Verifier' : id === 'user' ? 'You' : names.current[id] ?? id;
  const fileName = (id: string) => files.find((f) => f.id === id)?.name ?? fileNames.current[id] ?? id;

  const refresh = async (id: string) => {
    const [f, a, s, m, n] = await Promise.all([
      backend.listFiles(id), backend.listAgents(id), backend.listSessions(id), backend.getContextMap(id), backend.listNotes(id),
    ]);
    fileNames.current = Object.fromEntries(f.map((x) => [x.id, x.name]));
    setNotes(n);
    names.current = Object.fromEntries(a.map((x) => [x.id, x.name]));
    setFiles(f); setAgents(a); setSessions(s); setMap(m);
    return s;
  };

  const loadWs = async (id: string) => {
    ctrl.current?.abort();
    setRunning(false); setHuddle(emptyHuddle); setCite(null); setCard(null);
    const s = await refresh(id);
    setWs(id);
    setSid(s[0]?.id ?? null);
  };

  useEffect(() => {
    backend.listWorkspaces().then((list) => {
      setWorkspaces(list);
      if (list[0]) loadWs(list[0].id);
    });
  }, []);

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { clock.paused = paused; clock.speed = speed; }, [paused, speed]);

  // Load a session's stored messages the first time it is opened.
  useEffect(() => {
    if (sid && !msgs[sid]) backend.getMessages(ws, sid).then((m) => setMsgs((p) => (p[sid] ? p : { ...p, [sid]: m })));
  }, [sid]);

  const apply = (ev: AgentEvent, patch: (u: Partial<ChatMsg>) => void) => {
    const log = (h: Huddle, who: string, text: string, citations?: Citation[]) => [...h.log, { who, text, citations }];
    switch (ev.type) {
      case 'started':
        break;
      case 'status':
        patch({ status: ev.text });
        break;
      case 'broadcast':
        patch({ status: `The orchestrator is asking ${ev.to.length} translator${ev.to.length === 1 ? '' : 's'}` });
        setHuddle((h) => ({ ...h, pulse: h.pulse + 1, bubble: { agentId: ORCHESTRATOR, text: ev.text }, log: log(h, ORCHESTRATOR, ev.text) }));
        break;
      case 'join': {
        const text = `${nameOf(ev.agentId)} ${ev.how === 'called' ? 'was called into' : 'joined'} the huddle`;
        patch({ status: text });
        setHuddle((h) => ({ ...h, members: [...h.members, ev.agentId], log: log(h, 'system', text) }));
        break;
      }
      case 'assign': {
        const text = `${nameOf(ev.agentId)} was given ${fileName(ev.fileId)}`;
        patch({ status: text });
        setHuddle((h) => ({ ...h, working: { ...h.working, [ev.agentId]: ev.fileId }, log: log(h, 'system', text) }));
        break;
      }
      case 'note':
        setNotes((n) => [...n, ev.note]);
        setHuddle((h) => ({ ...h, log: log(h, 'system', `${nameOf(ev.note.authorId)} saved a note on ${fileName(ev.note.fileId)}`) }));
        break;
      case 'reading':
        patch({ status: `${nameOf(ev.agentId)} is reading` });
        setHuddle((h) => ({ ...h, reading: ev.agentId, bubble: null }));
        break;
      case 'say':
        patch({ status: 'The huddle is discussing your question' });
        setHuddle((h) => ({ ...h, reading: null, bubble: { agentId: ev.agentId, text: ev.text }, log: log(h, ev.agentId, ev.text, ev.citations) }));
        break;
      case 'verify': {
        const text = `The verifier is checking ${ev.claims.length} claim${ev.claims.length === 1 ? '' : 's'}`;
        patch({ status: text });
        setHuddle((h) => ({ ...h, verifier: { state: 'checking' }, bubble: null, reading: null, log: log(h, 'system', text) }));
        break;
      }
      case 'verdict': {
        const failed = ev.verdicts.filter((v) => v.verdict !== 'supported');
        setHuddle((h) => ({
          ...h, verifier: { state: ev.passed ? 'passed' : 'failed' },
          log: ev.passed ? log(h, 'system', 'Every claim was verified')
            : failed.reduce((l, v) => [...l, { who: VERIFIER, text: v.reason }], h.log),
        }));
        break;
      }
      case 'rehuddle':
        patch({ status: `Back to the huddle: round ${ev.round} of ${MAX_ROUNDS}` });
        setHuddle((h) => ({ ...h, log: log(h, 'system', `Round ${ev.round} of ${MAX_ROUNDS}`) }));
        break;
      case 'leave':
        setHuddle((h) => ({ ...h, members: h.members.filter((m) => !ev.agentIds.includes(m)), working: {}, bubble: null, reading: null, verifier: null, log: log(h, 'system', 'The huddle ended') }));
        break;
      case 'context':
        setMap((m) => ({ nodes: [...m.nodes, ...ev.nodes], links: [...m.links, ...ev.links] }));
        break;
      case 'answer':
        patch({ text: ev.text, citations: ev.citations, placeholder: ev.placeholder, unverified: ev.unverified, pending: false, status: undefined });
        break;
      case 'error':
        patch({ error: ev.message, pending: false, status: undefined });
        setHuddle((h) => ({ ...h, members: [], working: {}, bubble: null, reading: null, verifier: null }));
        break;
      case 'cancelled':
        patch({ text: 'The question was cancelled.', pending: false, status: undefined });
        setHuddle((h) => ({ ...h, members: [], working: {}, bubble: null, reading: null, verifier: null }));
        break;
    }
  };

  const send = async (text: string, wsId = ws, sessionId = sid) => {
    let s = sessionId;
    if (!s) {
      s = (await backend.createSession(wsId, text.slice(0, 60))).id;
      setSid(s);
    }
    const session = s;
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    const pending: ChatMsg = { id: uid(), role: 'assistant', text: '', pending: true, status: 'Passing your question to the orchestrator' };
    setMsgs((p) => ({ ...p, [session]: [...(p[session] ?? []).filter((m) => !m.pending), { id: uid(), role: 'user', text }, pending] }));
    setHuddle(emptyHuddle);
    setRunning(true);
    const patch = (u: Partial<ChatMsg>) =>
      setMsgs((p) => ({ ...p, [session]: (p[session] ?? []).map((m) => (m.id === pending.id ? { ...m, ...u } : m)) }));
    for await (const ev of backend.ask(wsId, session, text, c.signal)) {
      if (c.signal.aborted) return;
      apply(ev, patch);
    }
    if (c.signal.aborted) return;
    setRunning(false);
    setSessions(await backend.listSessions(wsId));
  };

  const runDemo = async () => {
    resetDemo();
    setPaused(false);
    await loadWs(DEMO_WORKSPACE.id);
    const session = await backend.createSession(DEMO_WORKSPACE.id, 'Demo: supplier price increase');
    setSessions(await backend.listSessions(DEMO_WORKSPACE.id));
    setSid(session.id);
    setMode((m) => (m === 'full' ? 'half' : m));
    send(DEMO_QUESTION, DEMO_WORKSPACE.id, session.id);
  };

  const upload = async (list: FileList) => {
    for (const f of Array.from(list)) await backend.uploadFile(ws, { name: f.name, size: f.size, data: f });
    await refresh(ws);
  };

  const newSession = async () => {
    const s = await backend.createSession(ws, 'New session');
    setSessions(await backend.listSessions(ws));
    setSid(s.id);
  };

  const createAgent = async (name: string, specialty: string) => {
    await backend.createAgent(ws, { name, specialty });
    const a = await backend.listAgents(ws);
    names.current = Object.fromEntries(a.map((x) => [x.id, x.name]));
    setAgents(a);
  };
  const addNote = async (fileId: string, text: string) => {
    await backend.addNote(ws, { fileId, text });
    setNotes(await backend.listNotes(ws));
  };
  const setWeight = async (noteIds: string[], weight: Weight) => {
    await backend.setNoteWeight(ws, noteIds, weight);
    setNotes(await backend.listNotes(ws));
  };
  const openCite = (c: Citation) => { setCite(c); setCard(null); };
  const noteActions: NoteActions = { nameOf, fileName, onWeight: setWeight, onCite: openCite };

  const newWorkspace = async () => {
    const name = prompt('Name of the new workspace');
    if (!name?.trim()) return;
    const created = await backend.createWorkspace(name.trim());
    setWorkspaces(await backend.listWorkspaces());
    loadWs(created.id);
  };
  const renameWorkspace = async () => {
    const current = workspaces.find((w) => w.id === ws);
    const name = prompt('New name of the workspace', current?.name ?? '');
    if (!name?.trim()) return;
    try {
      await backend.renameWorkspace(ws, name.trim());
      setWorkspaces(await backend.listWorkspaces());
    } catch (e) { alert((e as Error).message); }
  };
  const deleteWorkspace = async () => {
    const current = workspaces.find((w) => w.id === ws);
    if (!confirm(`Delete the workspace "${current?.name ?? ws}"?`)) return;
    try {
      await backend.deleteWorkspace(ws);
      const list = await backend.listWorkspaces();
      setWorkspaces(list);
      if (list[0]) loadWs(list[0].id);
    } catch (e) { alert((e as Error).message); }
  };

  const resize = (by: number) => setMode((m) => MODES[Math.min(2, Math.max(0, MODES.indexOf(m) + by))]);
  const cardAgent = card?.kind === 'agent' ? agents.find((a) => a.id === card.id) : undefined;
  const cardFile = card?.kind === 'file' ? files.find((f) => f.id === card.id) : undefined;

  return (
    <div className="app">
      <header className="topbar">
        <strong>Talk With Your Files</strong>
        <select value={ws} onChange={(e) => loadWs(e.target.value)} aria-label="Workspace">
          {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <span className="ws-actions">
          <button onClick={newWorkspace} title="New workspace">New</button>
          <button onClick={renameWorkspace} title="Rename this workspace">Rename</button>
          <button onClick={deleteWorkspace} title="Delete this workspace">Delete</button>
        </span>
        <span className="grow" />
        {running && (
          <span className="demo-controls">
            <button onClick={() => setPaused(!paused)}>{paused ? 'Play' : 'Pause'}</button>
            <button onClick={() => clock.step()}>Step</button>
            <button onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])} title="Speed">{speed}x</button>
          </span>
        )}
        <button className="primary" onClick={runDemo}>{ws === DEMO_WORKSPACE.id && (running || sid) ? 'Restart demo' : 'Run demo'}</button>
        <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? 'Light' : 'Dark'}</button>
      </header>

      <div className="body">
        <nav className="rail">
          {([['E', 'Files'], ['A', 'Agents'], ['S', 'Sessions'], ['C', 'Context map']] as const).map(([key, label]) => (
            <button key={key} className={panel === key ? 'on' : ''} title={label} aria-label={label}
              onClick={() => setPanel(panel === key ? null : key)}>{key}</button>
          ))}
        </nav>

        <main className={`main mode-${mode}`}>
          <Stage agents={agents} files={files} notes={notes} huddle={huddle} nameOf={nameOf}
            litAgent={cite?.agentId ?? cardAgent?.id ?? null} litFile={cite?.fileId ?? cardFile?.id ?? null}
            onAgent={(id) => { setCard({ kind: 'agent', id }); setCite(null); }}
            onFile={(id) => { setCard({ kind: 'file', id }); setCite(null); }}
            onMore={() => setPanel('A')} onCite={openCite} />
          <div className="divider">
            <span className="sizer">
              <button onClick={() => resize(-1)} disabled={mode === 'bar'} title="Make the chat smaller" aria-label="Make the chat smaller">↓</button>
              <button onClick={() => resize(1)} disabled={mode === 'full'} title="Make the chat bigger" aria-label="Make the chat bigger">↑</button>
            </span>
          </div>
          <Chat mode={mode} messages={sid ? msgs[sid] ?? [] : []} busy={running} hasFiles={files.length > 0}
            onSend={(t) => send(t)} onCite={openCite} />

          {panel === 'E' && <Explorer files={files} notes={notes} onUpload={upload} onFile={(id) => setCard({ kind: 'file', id })} onClose={() => setPanel(null)} />}
          {panel === 'A' && <AgentsPanel agents={agents} notes={notes} onAgent={(id) => setCard({ kind: 'agent', id })} onCreate={createAgent} onClose={() => setPanel(null)} />}
          {panel === 'S' && <Sessions sessions={sessions} current={sid} onOpen={setSid} onNew={newSession} onClose={() => setPanel(null)} />}
          {panel === 'C' && <ContextMapPanel map={map} onClose={() => setPanel(null)} />}
          {cite && <CitationPanel citation={cite} file={files.find((f) => f.id === cite.fileId)} foundBy={nameOf(cite.agentId)} onClose={() => setCite(null)} />}
          {cardFile && <FileCard key={cardFile.id} file={cardFile} notes={notes} actions={noteActions} onAddNote={(t) => addNote(cardFile.id, t)} onClose={() => setCard(null)} />}
          {cardAgent && <AgentCard key={cardAgent.id} ws={ws} agent={cardAgent} notes={notes} actions={noteActions} onClose={() => setCard(null)} />}
        </main>
      </div>
    </div>
  );
}
