import { expect, test } from 'vitest';
import schema from '../../../contract/schema.json';
import { httpBackend, parseSse } from './http';
import type { AgentEvent, Backend } from './types';

interface Call { method: string; path: string; body: unknown; headers: Record<string, string> }

function stub(respond: (call: Call) => Response = () => new Response('[]', { status: 200 })) {
  const calls: Call[] = [];
  const fetchFn = (async (url: string, init: RequestInit = {}) => {
    const call = {
      method: init.method ?? 'GET', path: new URL(url).pathname.replace('/api/v1', ''), body: init.body,
      headers: (init.headers ?? {}) as Record<string, string>,
    };
    calls.push(call);
    return respond(call);
  }) as unknown as typeof fetch;
  return { calls, backend: httpBackend('http://test', fetchFn) };
}

const blob = new Blob(['hello']);
const ARGS: Record<string, unknown[]> = {
  listWorkspaces: [], createWorkspace: ['W'], renameWorkspace: ['w1', 'W'], deleteWorkspace: ['w1'],
  listFiles: ['w1'], uploadFile: ['w1', { name: 'a.txt', size: 5, data: blob }],
  addFileVersion: ['w1', 'f1', { name: 'a.txt', size: 5, data: blob }], deleteFile: ['w1', 'f1'],
  listAgents: ['w1'], createAgent: ['w1', { name: 'A', specialty: 'generic' }], renameAgent: ['w1', 'a1', 'B'],
  deleteAgent: ['w1', 'a1'], listNotes: ['w1'], addNote: ['w1', { fileId: 'f1', text: 'x' }], editNote: ['w1', 'n1', 'y'],
  deleteNote: ['w1', 'n1'], setNoteWeight: ['w1', ['n1'], 'high'], listSessions: ['w1'], createSession: ['w1', 'S'],
  renameSession: ['w1', 's1', 'T'], deleteSession: ['w1', 's1'], getMessages: ['w1', 's1'], getContextMap: ['w1'],
  askTranslator: ['w1', 'a1', 'Q?'],
};
const IDS: Record<string, string> = { ws: 'w1', file_id: 'f1', agent_id: 'a1', note_id: 'n1', session_id: 's1' };

test('each method calls the method and path of its operation', async () => {
  const ops = schema.operations.filter((o) => o.backendMethod && o.name !== 'cancel_question' && o.name !== 'ask');
  expect(new Set(ops.map((o) => o.backendMethod))).toEqual(new Set(Object.keys(ARGS)));
  for (const op of ops) {
    const { calls, backend } = stub();
    const method = backend[op.backendMethod as keyof Backend] as (...args: unknown[]) => Promise<unknown>;
    await method(...ARGS[op.backendMethod as string]);
    expect(calls).toHaveLength(1);
    expect([calls[0].method, calls[0].path]).toEqual([op.method, op.path.replace(/{(\w+)}/g, (_, f: string) => IDS[f])]);
    expect(calls[0].headers['X-TWYF-Source']).toBe('ui');
    if (op.kind === 'upload') expect(calls[0].body).toBeInstanceOf(FormData);
  }
});

test('errors carry the backend message, and an upload needs its data', async () => {
  const { backend } = stub(() => new Response(JSON.stringify({ error: { code: 'not_found', message: 'No such workspace' } }), { status: 404 }));
  await expect(backend.listFiles('nope')).rejects.toThrow('No such workspace');
  await expect(stub().backend.uploadFile('w1', { name: 'a.txt', size: 1 })).rejects.toThrow();
});

const sse = (events: AgentEvent[]) => events.map((e, i) => `id: ${i + 1}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join('');

function chunked(text: string, size: number): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let at = 0;
  return new ReadableStream({
    pull(controller) {
      if (at >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(at, at + size));
      at += size;
    },
  });
}

test('the stream parser yields events split across network chunks', async () => {
  const events: AgentEvent[] = [
    { type: 'started', questionId: 'q1' }, { type: 'status', text: 'Reading — “café”' },
    { type: 'answer', text: 'Done [1].', citations: [] },
  ];
  for (const size of [1, 3, 7, 1000]) {
    const got: AgentEvent[] = [];
    for await (const e of parseSse(chunked(`: ping\n\n${sse(events)}`, size))) got.push(e);
    expect(got).toEqual(events);
  }
});

test('aborting the signal calls cancel_question', async () => {
  let release: () => void = () => undefined;
  const { calls, backend } = stub((call) => {
    if (call.path.endsWith('/questions')) {
      const first = new TextEncoder().encode(sse([{ type: 'started', questionId: 'q9' }, { type: 'status', text: 'Working' }]));
      return new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(first);
          release = () => controller.error(new DOMException('aborted', 'AbortError'));
        },
      }), { status: 200 });
    }
    return new Response(null, { status: 204 });
  });
  const controller = new AbortController();
  const seen: AgentEvent[] = [];
  for await (const e of backend.ask('w1', 's1', 'Q?', controller.signal)) {
    seen.push(e);
    if (e.type === 'status') {
      controller.abort();
      release();
    }
  }
  expect(seen.map((e) => e.type)).toEqual(['started', 'status']);
  await new Promise((r) => setTimeout(r, 0));
  expect(calls.map((c) => [c.method, c.path])).toContainEqual(['POST', '/workspaces/w1/questions/q9/cancel']);
});
