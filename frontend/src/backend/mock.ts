import { DEMO_QUESTION, DEMO_WORKSPACE, demoScript, demoWorkspace } from '../demo/scenario';
import type { ScriptStep } from '../demo/scenario';
import { ORCHESTRATOR } from './types';
import type { Agent, Backend, ChatMsg, Citation, ContextMap, FileItem, FileType, Session } from './types';

// An in-memory backend. Nothing is saved and nothing leaves the browser.

/** Paces the mock's events, so the demo can be paused, stepped and sped up. */
export const clock = {
  paused: false,
  speed: 1,
  skip: null as null | (() => void),
  wait(ms: number): Promise<void> {
    return new Promise((resolve) => {
      let left = ms;
      const done = () => {
        clearInterval(timer);
        clock.skip = null;
        resolve();
      };
      const timer = setInterval(() => {
        if (!clock.paused) left -= 50 * clock.speed;
        if (left <= 0) done();
      }, 50);
      clock.skip = done;
    });
  },
  /** Ends the current wait at once, so the next event arrives now. */
  step() {
    clock.skip?.();
  },
};

interface WsData {
  files: FileItem[];
  agents: Agent[];
  sessions: Session[];
  map: ContextMap;
  messages: Record<string, ChatMsg[]>;
}

const empty = (): WsData => ({ files: [], agents: [], sessions: [], map: { nodes: [], links: [] }, messages: {} });
const data: Record<string, WsData> = { mine: empty(), demo: structuredClone(demoWorkspace) };

export function resetDemo() {
  data.demo = structuredClone(demoWorkspace);
}

let counter = 0;
const uid = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${counter++}`;
const copy = <T,>(value: T): Promise<T> => Promise.resolve(structuredClone(value));

const TYPES: FileType[] = ['pdf', 'docx', 'csv', 'md', 'txt'];
const typeOf = (name: string): FileType => TYPES.find((t) => name.toLowerCase().endsWith(`.${t}`)) ?? 'other';

const placeholderCitation = (n: number, agent: Agent): Citation => ({
  n,
  fileId: agent.fileIds[0],
  agentId: agent.id,
  location: 'Placeholder location',
  passage: 'Placeholder passage. Real passages will come from the file once a backend is connected.',
  quote: 'Placeholder passage.',
});

/** A simulated huddle for any question that is not the demo question. */
function genericScript(ws: WsData, question: string): ScriptStep[] {
  if (!ws.agents.length) {
    return [{ delay: 600, event: { type: 'answer', citations: [], placeholder: true,
      text: 'There are no files in this workspace yet. Upload some in the explorer (E), or run the demo.' } }];
  }
  const q = question.toLowerCase();
  const called = ws.agents.filter((a) => q.includes(a.name.toLowerCase().replace(/\.[a-z0-9]+$/, '')));
  const joined = called.length ? called : ws.agents.slice(0, 2);
  const cites = joined.map((a, i) => placeholderCitation(i + 1, a));
  return [
    { delay: 800, event: { type: 'broadcast', to: ws.agents.map((a) => a.id), text: `Who can help with: "${question}"?` } },
    ...joined.map((a): ScriptStep => ({ delay: 900, event: { type: 'join', agentId: a.id, how: called.length ? 'called' : 'volunteered' } })),
    ...joined.flatMap((a, i): ScriptStep[] => [
      { delay: 900, event: { type: 'reading', agentId: a.id } },
      { delay: 1200, event: { type: 'say', agentId: a.id, citations: [cites[i]], text: `Placeholder: I would search ${a.name} for passages that answer this.` } },
    ]),
    { delay: 1500, event: { type: 'say', agentId: ORCHESTRATOR, text: 'Placeholder: I have what I need. Returning the findings.' } },
    { delay: 1200, event: { type: 'leave', agentIds: joined.map((a) => a.id) } },
    { delay: 900, event: { type: 'answer', citations: cites, placeholder: true,
      text: `No backend is connected yet, so this is a simulated answer. ${joined.map((a, i) => `${a.name} [${i + 1}]`).join(' and ')} took part in the huddle.` } },
  ];
}

export const mockBackend: Backend = {
  listWorkspaces: () => copy([{ id: 'mine', name: 'My workspace' }, DEMO_WORKSPACE]),
  listFiles: (ws) => copy(data[ws].files),
  listAgents: (ws) => copy(data[ws].agents),
  listSessions: (ws) => copy([...data[ws].sessions].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))),
  getMessages: (ws, sessionId) => copy(data[ws].messages[sessionId] ?? []),
  getContextMap: (ws) => copy(data[ws].map),

  createSession(ws, title) {
    const session: Session = { id: uid('s'), title, updatedAt: new Date().toISOString(), messageCount: 0 };
    data[ws].sessions.push(session);
    return copy(session);
  },

  async uploadFile(ws, { name, size }) {
    const id = uid('f');
    const type = typeOf(name);
    data[ws].files.push({
      id, name, type, sizeKb: Math.max(1, Math.round(size / 1024)), uploadedAt: new Date().toISOString(),
      summary: 'No summary yet. A translator will write one once a backend is connected.',
    });
    data[ws].agents.push({ id: id.replace('f-', 'a-'), name, fileIds: [id] });
    data[ws].map.nodes.push({ id, label: name, kind: 'file' });
  },

  async *ask(ws, sessionId, question, signal) {
    const script = ws === 'demo' && question.trim() === DEMO_QUESTION ? demoScript : genericScript(data[ws], question);
    for (const { delay, event } of script) {
      await clock.wait(delay);
      if (signal.aborted) return;
      if (event.type === 'context') {
        data[ws].map.nodes.push(...event.nodes);
        data[ws].map.links.push(...event.links);
      }
      yield structuredClone(event);
    }
    const session = data[ws].sessions.find((s) => s.id === sessionId);
    if (session) {
      session.messageCount += 2;
      session.updatedAt = new Date().toISOString();
    }
  },

  async askTranslator(ws, agentId) {
    await new Promise((resolve) => setTimeout(resolve, 600));
    const agent = data[ws].agents.find((a) => a.id === agentId)!;
    const file = data[ws].files.find((f) => f.id === agent.fileIds[0]);
    return { text: `Simulated reply. Here is what I hold: ${file?.summary ?? 'no files yet.'}`, citations: [] };
  },
};
