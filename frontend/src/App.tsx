import { useEffect, useRef, useState } from 'react';
import { backend } from './backend';
import { ORCHESTRATOR } from './backend/types';
import type { Agent, AgentEvent, ChatMsg, Citation, ContextMap, FileItem, Session, Workspace } from './backend/types';
import { Chat } from './Chat';
import type { ChatMode } from './Chat';
import { AgentCard, CitationPanel, ContextMapPanel, Explorer, Sessions } from './Panels';
import { Stage } from './Stage';
import type { Huddle } from './Stage';
// Demo-only imports: the "Run demo" button and its controls drive the mock's clock.
import { clock, resetDemo } from './backend/mock';
import { DEMO_QUESTION, DEMO_WORKSPACE } from './demo/scenario';

const emptyHuddle: Huddle = { members: [], bubble: null, reading: null, pulse: 0, log: [] };
const MODES: ChatMode[] = ['bar', 'half', 'full'];
const SPEEDS = [0.5, 1, 2, 4];
let counter = 0;
const uid = () => `m-${counter++}`;

export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [ws, setWs] = useState('mine');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [map, setMap] = useState<ContextMap>({ nodes: [], links: [] });
  const [sid, setSid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Record<string, ChatMsg[]>>({});
  const [huddle, setHuddle] = useState<Huddle>(emptyHuddle);
  const [mode, setMode] = useState<ChatMode>('half');
  const [panel, setPanel] = useState<null | 'E' | 'S' | 'C'>(null);
  const [cite, setCite] = useState<Citation | null>(null);
  const [card, setCard] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [theme, setTheme] = useState(() => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  const ctrl = useRef<AbortController | null>(null);
  const names = useRef<Record<string, string>>({});

  const nameOf = (id: string) => (id === ORCHESTRATOR ? 'Orchestrator' : names.current[id] ?? id);

  const refresh = async (id: string) => {
    const [f, a, s, m] = await Promise.all([
      backend.listFiles(id), backend.listAgents(id), backend.listSessions(id), backend.getContextMap(id),
    ]);
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
    backend.listWorkspaces().then(setWorkspaces);
    loadWs('mine');
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
      case 'reading':
        patch({ status: `${nameOf(ev.agentId)} is reading its file` });
        setHuddle((h) => ({ ...h, reading: ev.agentId, bubble: null }));
        break;
      case 'say':
        patch({ status: 'The huddle is discussing your question' });
        setHuddle((h) => ({ ...h, reading: null, bubble: { agentId: ev.agentId, text: ev.text }, log: log(h, ev.agentId, ev.text, ev.citations) }));
        break;
      case 'leave':
        setHuddle((h) => ({ ...h, members: h.members.filter((m) => !ev.agentIds.includes(m)), bubble: null, reading: null, log: log(h, 'system', 'The huddle ended') }));
        break;
      case 'context':
        setMap((m) => ({ nodes: [...m.nodes, ...ev.nodes], links: [...m.links, ...ev.links] }));
        break;
      case 'answer':
        patch({ text: ev.text, citations: ev.citations, placeholder: ev.placeholder, pending: false, status: undefined });
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
    for (const f of Array.from(list)) await backend.uploadFile(ws, { name: f.name, size: f.size });
    await refresh(ws);
  };

  const newSession = async () => {
    const s = await backend.createSession(ws, 'New session');
    setSessions(await backend.listSessions(ws));
    setSid(s.id);
  };

  const resize = (by: number) => setMode((m) => MODES[Math.min(2, Math.max(0, MODES.indexOf(m) + by))]);
  const cardAgent = agents.find((a) => a.id === card);

  return (
    <div className="app">
      <header className="topbar">
        <strong>Talk With Your Files</strong>
        <select value={ws} onChange={(e) => loadWs(e.target.value)} aria-label="Workspace">
          {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
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
          {([['E', 'Explorer'], ['S', 'Sessions'], ['C', 'Context map']] as const).map(([key, label]) => (
            <button key={key} className={panel === key ? 'on' : ''} title={label} aria-label={label}
              onClick={() => setPanel(panel === key ? null : key)}>{key}</button>
          ))}
        </nav>

        <main className={`main mode-${mode}`}>
          <Stage agents={agents} files={files} huddle={huddle} highlight={cite?.agentId ?? card} nameOf={nameOf}
            onAgent={(id) => { setCard(id); setCite(null); }} onMore={() => setPanel('E')} onCite={setCite} />
          <div className="divider">
            <span className="sizer">
              <button onClick={() => resize(-1)} disabled={mode === 'bar'} title="Make the chat smaller" aria-label="Make the chat smaller">↓</button>
              <button onClick={() => resize(1)} disabled={mode === 'full'} title="Make the chat bigger" aria-label="Make the chat bigger">↑</button>
            </span>
          </div>
          <Chat mode={mode} messages={sid ? msgs[sid] ?? [] : []} busy={running} hasFiles={files.length > 0}
            onSend={(t) => send(t)} onCite={(c) => { setCite(c); setCard(null); }} />

          {panel === 'E' && <Explorer files={files} agents={agents} onUpload={upload} onAgent={setCard} onClose={() => setPanel(null)} />}
          {panel === 'S' && <Sessions sessions={sessions} current={sid} onOpen={setSid} onNew={newSession} onClose={() => setPanel(null)} />}
          {panel === 'C' && <ContextMapPanel map={map} onClose={() => setPanel(null)} />}
          {cite && <CitationPanel citation={cite} file={files.find((f) => f.id === cite.fileId)} onClose={() => setCite(null)} />}
          {cardAgent && <AgentCard key={cardAgent.id} ws={ws} agent={cardAgent} files={files} onClose={() => setCard(null)} />}
        </main>
      </div>
    </div>
  );
}
