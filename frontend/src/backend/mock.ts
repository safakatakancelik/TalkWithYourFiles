import { DEMO_QUESTION, DEMO_WORKSPACE, demoScript, demoWorkspace } from '../demo/scenario';
import type { ScriptStep } from '../demo/scenario';
import { ORCHESTRATOR } from './types';
import type { Agent, Backend, ChatMsg, Citation, ContextMap, FileItem, FileType, Note, Session } from './types';

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
  notes: Note[];
  sessions: Session[];
  map: ContextMap;
  messages: Record<string, ChatMsg[]>;
}

// Every workspace starts with a small pool of generic translators.
const pool = (): Agent[] => [1, 2].map((n) => ({ id: `a-t${n}`, name: `Translator ${n}`, specialty: 'generic' }));
const empty = (): WsData => ({ files: [], agents: pool(), notes: [], sessions: [], map: { nodes: [], links: [] }, messages: {} });
const data: Record<string, WsData> = { mine: empty(), demo: structuredClone(demoWorkspace) };

export function resetDemo() {
  data.demo = structuredClone(demoWorkspace);
}

let counter = 0;
const uid = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${counter++}`;
const copy = <T,>(value: T): Promise<T> => Promise.resolve(structuredClone(value));

const TYPES: FileType[] = ['pdf', 'docx', 'csv', 'md', 'txt'];
const typeOf = (name: string): FileType => TYPES.find((t) => name.toLowerCase().endsWith(`.${t}`)) ?? 'other';

/** A simulated huddle for any question that is not the demo question. */
function genericScript(ws: WsData, question: string): ScriptStep[] {
  if (!ws.files.length) {
    return [{ delay: 600, event: { type: 'answer', citations: [], placeholder: true,
      text: 'There are no files in this workspace yet. Upload some in the explorer (E), or run the demo.' } }];
  }
  const q = question.toLowerCase();
  const named = ws.files.filter((f) => q.includes(f.name.toLowerCase().replace(/\.[a-z0-9]+$/, '')));
  // The orchestrator pairs files with translators from the pool. Nothing ties a translator to a file.
  const work = (named.length ? named : ws.files.slice(0, 2)).map((f, i) => ({ f, a: ws.agents[i % ws.agents.length] }));
  const joined = [...new Set(work.map((w) => w.a))];
  const cites = work.map(({ f, a }, i): Citation => ({
    n: i + 1, fileId: f.id, agentId: a.id, location: 'Placeholder location',
    passage: 'Placeholder passage. Real passages will come from the file once a backend is connected.',
    quote: 'Placeholder passage.',
  }));
  return [
    { delay: 800, event: { type: 'broadcast', to: ws.agents.map((a) => a.id), text: `Who can help with: "${question}"?` } },
    ...joined.map((a): ScriptStep => ({ delay: 900, event: { type: 'join', agentId: a.id, how: 'volunteered' } })),
    ...work.flatMap(({ f, a }, i): ScriptStep[] => {
      const text = `Placeholder: I would search ${f.name} for passages that answer this.`;
      return [
        { delay: 900, event: { type: 'assign', agentId: a.id, fileId: f.id } },
        { delay: 700, event: { type: 'reading', agentId: a.id } },
        { delay: 1200, event: { type: 'say', agentId: a.id, citations: [cites[i]], text } },
        { delay: 400, event: { type: 'note', note: {
          id: uid('n'), fileId: f.id, authorId: a.id, kind: 'finding', text, citations: [cites[i]],
          createdAt: new Date().toISOString(), weight: 'normal' } } },
      ];
    }),
    { delay: 1500, event: { type: 'say', agentId: ORCHESTRATOR, text: 'Placeholder: I have what I need. Returning the findings.' } },
    { delay: 1200, event: { type: 'leave', agentIds: joined.map((a) => a.id) } },
    { delay: 900, event: { type: 'answer', citations: cites, placeholder: true,
      text: `No backend is connected yet, so this is a simulated answer. The huddle looked at ${work.map((w, i) => `${w.f.name} [${i + 1}]`).join(' and ')}.` } },
  ];
}

export const mockBackend: Backend = {
  listWorkspaces: () => copy([{ id: 'mine', name: 'My workspace' }, DEMO_WORKSPACE]),
  listFiles: (ws) => copy(data[ws].files),
  listAgents: (ws) => copy(data[ws].agents),
  listSessions: (ws) => copy([...data[ws].sessions].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))),
  getMessages: (ws, sessionId) => copy(data[ws].messages[sessionId] ?? []),
  listNotes: (ws) => copy(data[ws].notes),
  getContextMap: (ws) => copy(data[ws].map),

  async setNoteWeight(ws, noteIds, weight) {
    for (const n of data[ws].notes) if (noteIds.includes(n.id)) n.weight = weight;
  },

  createSession(ws, title) {
    const session: Session = { id: uid('s'), title, updatedAt: new Date().toISOString(), messageCount: 0 };
    data[ws].sessions.push(session);
    return copy(session);
  },

  async uploadFile(ws, { name, size }) {
    const id = uid('f');
    const type = typeOf(name);
    // The file is stored on its own. No agent is created for it.
    data[ws].files.push({ id, name, type, sizeKb: Math.max(1, Math.round(size / 1024)), uploadedAt: new Date().toISOString() });
    data[ws].map.nodes.push({ id, label: name, kind: 'file' });
  },

  async createAgent(ws, { name, specialty }) {
    data[ws].agents.push({ id: uid('a'), name, specialty });
  },

  async addNote(ws, { fileId, text }) {
    data[ws].notes.push({
      id: uid('n'), fileId, authorId: 'user', kind: 'interpretation', text, citations: [],
      createdAt: new Date().toISOString(), weight: 'normal',
    });
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
      if (event.type === 'note') data[ws].notes.push(structuredClone(event.note));
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
    const mine = data[ws].notes.filter((n) => n.authorId === agentId && n.weight !== 'off');
    const text = mine.length
      ? `Simulated reply. I have ${mine.length} active note${mine.length === 1 ? '' : 's'} here. The latest: ${mine[mine.length - 1].text}`
      : 'Simulated reply. I have not written any notes in this workspace yet.';
    return { text, citations: [] };
  },
};
