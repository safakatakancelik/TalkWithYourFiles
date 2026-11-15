import { expect, test } from 'vitest';
import { clock, mockBackend, resetDemo } from '../backend/mock';
import type { AgentEvent, Backend } from '../backend/types';
import { DEMO_QUESTION, DEMO_WORKSPACE } from './scenario';

// Runs the demo scenario through the Backend interface only.
// To test a real backend later, load the demo files into it and pass it in place of mockBackend.
const backend: Backend = mockBackend;
const ws = DEMO_WORKSPACE.id;

test('the demo question triggers every kind of agent work and a fully cited answer', async () => {
  resetDemo();
  clock.speed = 1000;
  const [files, agents, before, notesBefore] = await Promise.all([
    backend.listFiles(ws), backend.listAgents(ws), backend.getContextMap(ws), backend.listNotes(ws),
  ]);
  const session = await backend.createSession(ws, 'test');

  const events: AgentEvent[] = [];
  for await (const event of backend.ask(ws, session.id, DEMO_QUESTION, new AbortController().signal)) events.push(event);
  const of = <T extends AgentEvent['type']>(type: T) => events.filter((e): e is Extract<AgentEvent, { type: T }> => e.type === type);

  // The orchestrator asks every translator.
  expect(of('broadcast')[0].to.sort()).toEqual(agents.map((a) => a.id).sort());

  // Three volunteer, one is called directly, one stays out.
  const joins = of('join');
  expect(joins.filter((j) => j.how === 'volunteered')).toHaveLength(3);
  expect(joins.filter((j) => j.how === 'called').map((j) => j.agentId)).toEqual(['a-t2']);
  expect(agents.length - joins.length).toBe(1);

  // Files and translators are independent: the orchestrator pairs them per question.
  const assigns = of('assign');
  expect(assigns.map((a) => a.agentId).sort()).toEqual(joins.map((j) => j.agentId).sort());
  for (const a of assigns) expect(files.some((f) => f.id === a.fileId)).toBe(true);

  // Each translator stores what it found as a note on the file it was given, with a citation into that file.
  const written = of('note').map((e) => e.note);
  expect(written).toHaveLength(4);
  for (const n of written) {
    expect(assigns.some((a) => a.agentId === n.authorId && a.fileId === n.fileId)).toBe(true);
    expect(n.citations.length).toBeGreaterThan(0);
    for (const c of n.citations) expect(c.fileId).toBe(n.fileId);
  }
  expect((await backend.listNotes(ws)).length).toBe(notesBefore.length + 4);

  // A note can be turned off without touching the file or the agent.
  await backend.setNoteWeight(ws, [written[0].id], 'off');
  expect((await backend.listNotes(ws)).find((n) => n.id === written[0].id)?.weight).toBe('off');

  // Only agents in the huddle speak, and everyone leaves before the answer.
  const members = new Set(['orchestrator', ...joins.map((j) => j.agentId)]);
  for (const say of of('say')) expect(members.has(say.agentId)).toBe(true);
  expect(of('leave').flatMap((l) => l.agentIds).sort()).toEqual(joins.map((j) => j.agentId).sort());
  expect(events.at(-1)?.type).toBe('answer');

  // Every marker in the answer has a citation, and every citation points at a real file and its translator.
  const answer = of('answer')[0];
  const markers = [...answer.text.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
  expect(new Set(markers)).toEqual(new Set(answer.citations.map((c) => c.n)));
  for (const c of answer.citations) {
    expect(files.some((f) => f.id === c.fileId)).toBe(true);
    expect(agents.some((a) => a.id === c.agentId)).toBe(true);
    expect(c.passage).toContain(c.quote);
  }

  // The context map grows.
  const after = await backend.getContextMap(ws);
  expect(after.nodes.length).toBeGreaterThan(before.nodes.length);
});
