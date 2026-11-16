import { DEMO_WORKSPACE } from '../demo/scenario';
import type { Backend } from './types';

/** Sends every call for the demo workspace to the mock, so "Run demo" always plays the scripted story. */
export function withDemo(real: Backend, mock: Backend): Backend {
  const pick = (ws: string) => (ws === DEMO_WORKSPACE.id ? mock : real);
  return {
    listWorkspaces: async () => [...(await real.listWorkspaces()).filter((w) => w.id !== DEMO_WORKSPACE.id), DEMO_WORKSPACE],
    createWorkspace: (name) => real.createWorkspace(name),
    renameWorkspace: (ws, name) => pick(ws).renameWorkspace(ws, name),
    deleteWorkspace: (ws) => pick(ws).deleteWorkspace(ws),
    listFiles: (ws) => pick(ws).listFiles(ws),
    uploadFile: (ws, file) => pick(ws).uploadFile(ws, file),
    addFileVersion: (ws, fileId, file) => pick(ws).addFileVersion(ws, fileId, file),
    deleteFile: (ws, fileId) => pick(ws).deleteFile(ws, fileId),
    listAgents: (ws) => pick(ws).listAgents(ws),
    createAgent: (ws, agent) => pick(ws).createAgent(ws, agent),
    renameAgent: (ws, agentId, name) => pick(ws).renameAgent(ws, agentId, name),
    deleteAgent: (ws, agentId) => pick(ws).deleteAgent(ws, agentId),
    listNotes: (ws) => pick(ws).listNotes(ws),
    addNote: (ws, note) => pick(ws).addNote(ws, note),
    editNote: (ws, noteId, text) => pick(ws).editNote(ws, noteId, text),
    deleteNote: (ws, noteId) => pick(ws).deleteNote(ws, noteId),
    setNoteWeight: (ws, noteIds, weight) => pick(ws).setNoteWeight(ws, noteIds, weight),
    listSessions: (ws) => pick(ws).listSessions(ws),
    createSession: (ws, title) => pick(ws).createSession(ws, title),
    renameSession: (ws, sessionId, title) => pick(ws).renameSession(ws, sessionId, title),
    deleteSession: (ws, sessionId) => pick(ws).deleteSession(ws, sessionId),
    getMessages: (ws, sessionId) => pick(ws).getMessages(ws, sessionId),
    getContextMap: (ws) => pick(ws).getContextMap(ws),
    ask: (ws, sessionId, question, signal) => pick(ws).ask(ws, sessionId, question, signal),
    askTranslator: (ws, agentId, question) => pick(ws).askTranslator(ws, agentId, question),
  };
}
