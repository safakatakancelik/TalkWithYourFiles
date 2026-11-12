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
  summary: string;
}

/** A translator agent. It has one file today, but may hold zero or many. */
export interface Agent {
  id: string;
  name: string;
  fileIds: string[];
}

export interface Citation {
  n: number;
  fileId: string;
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
  | { type: 'reading'; agentId: string }
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
  getContextMap(ws: string): Promise<ContextMap>;
  createSession(ws: string, title: string): Promise<Session>;
  uploadFile(ws: string, file: { name: string; size: number }): Promise<void>;
  ask(ws: string, sessionId: string, question: string, signal: AbortSignal): AsyncIterable<AgentEvent>;
  askTranslator(ws: string, agentId: string, question: string): Promise<{ text: string; citations: Citation[] }>;
}
