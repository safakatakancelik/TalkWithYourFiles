// The whole contract between the UI and any backend. The UI imports nothing else from a backend.

export type FileType = 'pdf' | 'docx' | 'csv' | 'md' | 'txt' | 'image' | 'other';

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
  status?: 'processing' | 'ready' | 'unreadable' | 'missing' | 'changed';
  /** The number of the file's current version, from 1. */
  version?: number;
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
  /** An agent id, ORCHESTRATOR, VERIFIER or 'user'. */
  authorId: string;
  kind: 'summary' | 'interpretation' | 'finding';
  text: string;
  /** Required for a summary or finding written by an agent. An interpretation is guidance and may have none. */
  citations: Citation[];
  createdAt: string;
  /** How much later work should rely on this note. 'off' disables it. */
  weight: Weight;
  authorName?: string;
  /** The version of the file this note was written about. */
  fileVersion?: number;
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
  id?: string;
  extractionId?: string;
  /** Character offsets of the quote in the file's extracted text. */
  start?: number;
  end?: number;
  page?: number;
  fileName?: string;
  /** The version of the file this passage was quoted from. */
  fileVersion?: number;
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
  unverified?: Unverified[];
  error?: string;
}

export interface Unverified { text: string; reason: string }

export interface Claim {
  id: string;
  text: string;
  kind: 'quoted' | 'derived';
  /** The `n` of each citation that supports this claim. */
  citations: number[];
  derivedFrom?: string[];
  calculation?: string;
}

export interface Verdict {
  claimId: string;
  verdict: 'supported' | 'partly_supported' | 'unsupported' | 'mechanical_fail';
  reason: string;
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
export const VERIFIER = 'verifier';

/** What a backend streams while a question is being answered. `agentId` may be ORCHESTRATOR in `say`. */
export type AgentEvent =
  | { type: 'started'; questionId: string }
  | { type: 'status'; text: string }
  | { type: 'broadcast'; text: string; to: string[] }
  | { type: 'join'; agentId: string; how: 'volunteered' | 'called' }
  | { type: 'assign'; agentId: string; fileId: string }
  | { type: 'reading'; agentId: string }
  | { type: 'note'; note: Note }
  | { type: 'say'; agentId: string; text: string; citations?: Citation[] }
  | { type: 'verify'; round: number; claims: Claim[]; citations: Citation[] }
  | { type: 'verdict'; round: number; passed: boolean; verdicts: Verdict[] }
  | { type: 'rehuddle'; round: number; reason: string; claimIds: string[] }
  | { type: 'leave'; agentIds: string[] }
  | { type: 'context'; nodes: MapNode[]; links: MapLink[] }
  | { type: 'answer'; text: string; citations: Citation[]; placeholder?: boolean; unverified?: Unverified[] }
  | { type: 'error'; code: string; message: string }
  | { type: 'cancelled' };

export interface Backend {
  listWorkspaces(): Promise<Workspace[]>;
  createWorkspace(name: string): Promise<Workspace>;
  renameWorkspace(ws: string, name: string): Promise<Workspace>;
  deleteWorkspace(ws: string): Promise<void>;
  listFiles(ws: string): Promise<FileItem[]>;
  listAgents(ws: string): Promise<Agent[]>;
  listSessions(ws: string): Promise<Session[]>;
  getMessages(ws: string, sessionId: string): Promise<ChatMsg[]>;
  listNotes(ws: string): Promise<Note[]>;
  setNoteWeight(ws: string, noteIds: string[], weight: Weight): Promise<void>;
  getContextMap(ws: string): Promise<ContextMap>;
  createSession(ws: string, title: string): Promise<Session>;
  uploadFile(ws: string, file: { name: string; size: number; data?: Blob }): Promise<void>;
  /** Adds new content to an existing file as its next version. Notes stay with the file. */
  addFileVersion(ws: string, fileId: string, file: { name: string; size: number; data?: Blob }): Promise<void>;
  deleteFile(ws: string, fileId: string): Promise<void>;
  /** Adds a translator to the workspace's pool. */
  createAgent(ws: string, agent: { name: string; specialty: string }): Promise<void>;
  renameAgent(ws: string, agentId: string, name: string): Promise<void>;
  deleteAgent(ws: string, agentId: string): Promise<void>;
  /** Adds a note written by the user about a file. */
  addNote(ws: string, note: { fileId: string; text: string }): Promise<void>;
  /** Only a note written by the user can be edited. */
  editNote(ws: string, noteId: string, text: string): Promise<void>;
  deleteNote(ws: string, noteId: string): Promise<void>;
  renameSession(ws: string, sessionId: string, title: string): Promise<void>;
  deleteSession(ws: string, sessionId: string): Promise<void>;
  ask(ws: string, sessionId: string, question: string, signal: AbortSignal): AsyncIterable<AgentEvent>;
  askTranslator(ws: string, agentId: string, question: string): Promise<{ text: string; citations: Citation[] }>;
}
