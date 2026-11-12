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
  const [files, agents, before] = await Promise.all([backend.listFiles(ws), backend.listAgents(ws), backend.getContextMap(ws)]);
  const session = await backend.createSession(ws, 'test');

  const events: AgentEvent[] = [];
  for await (const event of backend.ask(ws, session.id, DEMO_QUESTION, new AbortController().signal)) events.push(event);
  const of = <T extends AgentEvent['type']>(type: T) => events.filter((e): e is Extract<AgentEvent, { type: T }> => e.type === type);

  // The orchestrator asks every translator.
  expect(of('broadcast')[0].to.sort()).toEqual(agents.map((a) => a.id).sort());

  // Three volunteer, one is called directly, two stay out.
  const joins = of('join');
  expect(joins.filter((j) => j.how === 'volunteered')).toHaveLength(3);
  expect(joins.filter((j) => j.how === 'called').map((j) => j.agentId)).toEqual(['a-pricing']);
  expect(agents.length - joins.length).toBe(2);

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
    expect(agents.find((a) => a.id === c.agentId)?.fileIds).toContain(c.fileId);
    expect(c.passage).toContain(c.quote);
  }

  // The context map grows.
  const after = await backend.getContextMap(ws);
  expect(after.nodes.length).toBeGreaterThan(before.nodes.length);
});
