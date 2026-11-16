import { expect, test } from 'vitest';
import { httpBackend } from '../backend/http';
import { clock, mockBackend, resetDemo } from '../backend/mock';
import type { AgentEvent, Backend } from '../backend/types';
import { DEMO_QUESTION, DEMO_WORKSPACE } from './scenario';

// Runs the demo scenario through the Backend interface only: on the mock, or with TWYF_TEST_BACKEND_URL set,
// on a real server started by backend/scripts/run_demo_server.sh.
const url = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.TWYF_TEST_BACKEND_URL;
const backend: Backend = url ? httpBackend(url) : mockBackend;
const ws = DEMO_WORKSPACE.id;

test('the demo question triggers every kind of agent work and a fully cited answer', { timeout: 60_000 }, async () => {
  if (!url) {
    resetDemo();
    clock.speed = 1000;
  }
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
  expect(written).toHaveLength(5);
  for (const n of written) {
    expect(assigns.some((a) => a.agentId === n.authorId && a.fileId === n.fileId)).toBe(true);
    expect(n.citations.length).toBeGreaterThan(0);
    for (const c of n.citations) expect(c.fileId).toBe(n.fileId);
  }
  expect((await backend.listNotes(ws)).length).toBe(notesBefore.length + 5);

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

  // Verification (10-demo-scenario.md section 6).
  expect(events[0].type).toBe('started');
  for (const n of notesBefore.filter((x) => x.kind === 'summary' && x.authorId !== 'user')) {
    expect(n.citations.length).toBeGreaterThan(0);
    for (const c of n.citations) expect(c.passage).toContain(c.quote);
  }
  for (const say of of('say').filter((x) => x.agentId !== 'orchestrator')) expect(say.citations?.length ?? 0).toBeGreaterThan(0);
  expect(of('say').some((x) => x.agentId === 'verifier')).toBe(false);
  const verifies = of('verify');
  const verdicts = of('verdict');
  expect(verifies).toHaveLength(2);
  expect(verdicts).toHaveLength(2);
  expect(verdicts[0].passed).toBe(false);
  expect(verdicts[0].verdicts.filter((v) => v.verdict !== 'supported')).toHaveLength(1);
  const index = (e: AgentEvent) => events.indexOf(e);
  for (const v of verifies) {
    const next = verdicts.find((d) => index(d) > index(v));
    expect(next?.verdicts.map((x) => x.claimId).sort()).toEqual(v.claims.map((c) => c.id).sort());
  }
  const rehuddles = of('rehuddle');
  expect(rehuddles).toHaveLength(1);
  expect(rehuddles[0].round).toBe(2);
  expect(rehuddles[0].claimIds).toEqual(verdicts[0].verdicts.filter((v) => v.verdict !== 'supported').map((v) => v.claimId));
  expect(index(rehuddles[0])).toBe(index(verdicts[0]) + 1);
  const between = events.slice(index(rehuddles[0]), index(verifies[1]));
  expect(between.some((e) => e.type === 'say' && (e.citations?.length ?? 0) > 0)).toBe(true);
  expect(verdicts[1].passed).toBe(true);
  expect(index(of('leave')[0])).toBeGreaterThan(index(verdicts[1]));
  expect(answer.unverified ?? []).toHaveLength(0);
});
