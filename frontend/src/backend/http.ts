import type { AgentEvent, Backend } from './types';

// The real backend, over HTTP. The API is described by contract/schema.json.

/** Reads a server-sent event stream and yields each event's JSON `data`, however the bytes are split. */
export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncIterable<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let end: number;
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = block.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('\n');
        if (data) yield JSON.parse(data) as AgentEvent;
      }
      if (done) return;
    }
  } finally {
    reader.releaseLock();
  }
}

export function httpBackend(baseUrl: string, fetchFn: typeof fetch = fetch): Backend {
  const api = `${baseUrl.replace(/\/$/, '')}/api/v1`;
  const p = encodeURIComponent;
  const headers = { 'X-TWYF-Source': 'ui' };

  async function call(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
    const init: RequestInit = { method, headers: { ...headers }, signal };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) {
      init.headers = { ...headers, 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    const response = await fetchFn(`${api}${path}`, init);
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.error?.message ?? `The backend answered ${response.status}`);
    }
    return response;
  }
  const json = async <T,>(method: string, path: string, body?: unknown): Promise<T> => (await call(method, path, body)).json();
  const none = async (method: string, path: string, body?: unknown): Promise<void> => {
    await call(method, path, body);
  };
  const form = (file: { name: string; data?: Blob }) => {
    if (!file.data) throw new Error('The file has no data to upload.');
    const body = new FormData();
    body.append('file', file.data, file.name);
    return body;
  };

  return {
    listWorkspaces: () => json('GET', '/workspaces'),
    createWorkspace: (name) => json('POST', '/workspaces', { name }),
    renameWorkspace: (ws, name) => json('PATCH', `/workspaces/${p(ws)}`, { name }),
    deleteWorkspace: (ws) => none('DELETE', `/workspaces/${p(ws)}`),
    listFiles: (ws) => json('GET', `/workspaces/${p(ws)}/files`),
    uploadFile: async (ws, file) => none('POST', `/workspaces/${p(ws)}/files`, form(file)),
    addFileVersion: async (ws, fileId, file) => none('POST', `/workspaces/${p(ws)}/files/${p(fileId)}/versions`, form(file)),
    deleteFile: (ws, fileId) => none('DELETE', `/workspaces/${p(ws)}/files/${p(fileId)}`),
    listAgents: (ws) => json('GET', `/workspaces/${p(ws)}/agents`),
    createAgent: (ws, agent) => none('POST', `/workspaces/${p(ws)}/agents`, agent),
    renameAgent: (ws, agentId, name) => none('PATCH', `/workspaces/${p(ws)}/agents/${p(agentId)}`, { name }),
    deleteAgent: (ws, agentId) => none('DELETE', `/workspaces/${p(ws)}/agents/${p(agentId)}`),
    listNotes: (ws) => json('GET', `/workspaces/${p(ws)}/notes`),
    addNote: (ws, note) => none('POST', `/workspaces/${p(ws)}/notes`, note),
    editNote: (ws, noteId, text) => none('PATCH', `/workspaces/${p(ws)}/notes/${p(noteId)}`, { text }),
    deleteNote: (ws, noteId) => none('DELETE', `/workspaces/${p(ws)}/notes/${p(noteId)}`),
    setNoteWeight: (ws, noteIds, weight) => none('POST', `/workspaces/${p(ws)}/notes/weight`, { noteIds, weight }),
    listSessions: (ws) => json('GET', `/workspaces/${p(ws)}/sessions`),
    createSession: (ws, title) => json('POST', `/workspaces/${p(ws)}/sessions`, { title }),
    renameSession: (ws, sessionId, title) => none('PATCH', `/workspaces/${p(ws)}/sessions/${p(sessionId)}`, { title }),
    deleteSession: (ws, sessionId) => none('DELETE', `/workspaces/${p(ws)}/sessions/${p(sessionId)}`),
    getMessages: (ws, sessionId) => json('GET', `/workspaces/${p(ws)}/sessions/${p(sessionId)}/messages`),
    getContextMap: (ws) => json('GET', `/workspaces/${p(ws)}/context-map`),
    askTranslator: (ws, agentId, question) => json('POST', `/workspaces/${p(ws)}/agents/${p(agentId)}/ask`, { question }),

    async *ask(ws, sessionId, question, signal) {
      // Closing the stream does not cancel a question; only cancel_question does, once its id is known.
      const stream = new AbortController();
      let questionId: string | null = null;
      const cancel = () => {
        stream.abort();
        if (questionId) void call('POST', `/workspaces/${p(ws)}/questions/${p(questionId)}/cancel`).catch(() => undefined);
      };
      if (signal.aborted) return;
      signal.addEventListener('abort', cancel, { once: true });
      try {
        const response = await call('POST', `/workspaces/${p(ws)}/sessions/${p(sessionId)}/questions`, { question }, stream.signal);
        if (!response.body) throw new Error('The backend sent no event stream.');
        for await (const event of parseSse(response.body)) {
          if (event.type === 'started') {
            questionId = event.questionId;
            if (signal.aborted) cancel();
          }
          if (signal.aborted) return;
          yield event;
        }
      } catch (error) {
        if (signal.aborted) return;
        throw error;
      } finally {
        signal.removeEventListener('abort', cancel);
      }
    },
  };
}
