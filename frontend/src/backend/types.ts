// The whole contract between the UI and any backend. The UI imports nothing else from a backend.

export type FileType = 'pdf' | 'docx' | 'csv' | 'md' | 'txt' | 'other';

export interface Workspace {
  id: string;
  name: string;
}

export interface FileItem {
  id: string;
  name: string;
  type: FileType;
  sizeKb: number;
  uploadedAt: string;
}

/**
 * A translator agent from the workspace's pool. Agents and files never refer to each other:
 * the orchestrator assigns files per question, and notes record what an agent made of a file.
 */
export interface Agent {
  id: string;
  name: string;
  /** 'generic', or the speciality of a specialised translator. */
  specialty: string;
}

export type Weight = 'off' | 'low' | 'normal' | 'high';
export const WEIGHTS: Weight[] = ['off', 'low', 'normal', 'high'];

/** What someone made of a file: a summary, an interpretation or a finding. The only link between files and agents. */
export interface Note {
  id: string;
  fileId: string;
  /** An agent id, ORCHESTRATOR or 'user'. */
  authorId: string;
  kind: 'summary' | 'interpretation' | 'finding';
  text: string;
  citations: Citation[];
  createdAt: string;
  /** How much later work should rely on this note. 'off' disables it. */
  weight: Weight;
}

export interface Citation {
  n: number;
  fileId: string;
  /** The agent that found the passage. */
  agentId: string;
  location: string;
  passage: string;
  /** The part of the passage to highlight. */
  quote: string;
}

export interface Session {
  id: string;
  title: string;
  updatedAt: string;
  messageCount: number;
}

export interface ChatMsg {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  pending?: boolean;
  status?: string;
  placeholder?: boolean;
}

export interface MapNode {
  id: string;
  label: string;
  kind: 'file' | 'entity';
}

export interface MapLink {
  from: string;
  to: string;
}

export interface ContextMap {
  nodes: MapNode[];
  links: MapLink[];
}

export const ORCHESTRATOR = 'orchestrator';

/** What a backend streams while a question is being answered. `agentId` may be ORCHESTRATOR in `say`. */
export type AgentEvent =
  | { type: 'status'; text: string }
  | { type: 'broadcast'; text: string; to: string[] }
  | { type: 'join'; agentId: string; how: 'volunteered' | 'called' }
  | { type: 'assign'; agentId: string; fileId: string }
  | { type: 'reading'; agentId: string }
  | { type: 'note'; note: Note }
  | { type: 'say'; agentId: string; text: string; citations?: Citation[] }
  | { type: 'leave'; agentIds: string[] }
  | { type: 'context'; nodes: MapNode[]; links: MapLink[] }
  | { type: 'answer'; text: string; citations: Citation[]; placeholder?: boolean };

export interface Backend {
  listWorkspaces(): Promise<Workspace[]>;
  listFiles(ws: string): Promise<FileItem[]>;
  listAgents(ws: string): Promise<Agent[]>;
  listSessions(ws: string): Promise<Session[]>;
  getMessages(ws: string, sessionId: string): Promise<ChatMsg[]>;
  listNotes(ws: string): Promise<Note[]>;
  setNoteWeight(ws: string, noteIds: string[], weight: Weight): Promise<void>;
  getContextMap(ws: string): Promise<ContextMap>;
  createSession(ws: string, title: string): Promise<Session>;
  uploadFile(ws: string, file: { name: string; size: number }): Promise<void>;
  /** Adds a translator to the workspace's pool. */
  createAgent(ws: string, agent: { name: string; specialty: string }): Promise<void>;
  /** Adds a note written by the user about a file. */
  addNote(ws: string, note: { fileId: string; text: string }): Promise<void>;
  ask(ws: string, sessionId: string, question: string, signal: AbortSignal): AsyncIterable<AgentEvent>;
  askTranslator(ws: string, agentId: string, question: string): Promise<{ text: string; citations: Citation[] }>;
}
