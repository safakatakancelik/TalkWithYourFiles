import { expect, test } from 'vitest';
import { ORCHESTRATOR, VERIFIER } from './backend/types';
import type { AgentEvent } from './backend/types';
import { demoScript } from './demo/scenario';
import type { Huddle } from './Stage';
import { tell } from './story';

const start: Huddle = { active: false, members: [], working: {}, bubble: null, reading: null, pulse: 0, log: [], verifier: null, busy: {}, now: null, flights: [] };

/** Plays events through `tell`, with the members and files kept as the app keeps them, and returns who was busy after each. */
function play(events: AgentEvent[]) {
  let h = start;
  return events.map((ev) => {
    h = { ...h, ...tell(h, ev, (id) => id, (id) => id, 0) };
    if (ev.type === 'join') h = { ...h, members: [...h.members, ev.agentId] };
    if (ev.type === 'assign') h = { ...h, working: { ...h.working, [ev.agentId]: ev.fileId } };
    if (ev.type === 'leave') h = { ...h, members: h.members.filter((m) => !ev.agentIds.includes(m)) };
    return { ev, busy: h.busy, now: h.now?.text ?? null, flights: h.flights };
  });
}

test('the demo tells who is working at every step, and someone always is until the answer', () => {
  const story = play(demoScript.map((s) => s.event));
  const after = (match: (ev: AgentEvent) => boolean) => story.find((s) => match(s.ev))!;

  expect(after((e) => e.type === 'started').busy).toEqual({ [ORCHESTRATOR]: 'planning' });
  const broadcast = after((e) => e.type === 'broadcast');
  expect(Object.values(broadcast.busy).every((d) => d === 'deciding')).toBe(true);
  expect(broadcast.flights.every((f) => f.from === ORCHESTRATOR)).toBe(true);

  // Joining ends the deciding; reading puts the reader to work, with its file.
  expect(after((e) => e.type === 'join').busy).toEqual({});
  expect(after((e) => e.type === 'reading').busy).toEqual({ 'a-contracts': 'reading f-contract' });

  // The last translator to report back hands over to the orchestrator.
  const said = after((e) => e.type === 'say' && e.agentId === 'a-contracts');
  expect(said.busy).toEqual({ [ORCHESTRATOR]: 'reviewing' });
  expect(said.flights.at(-1)).toMatchObject({ from: 'a-contracts', to: ORCHESTRATOR });

  expect(after((e) => e.type === 'verify').busy).toEqual({ [VERIFIER]: 'checking claims' });
  expect(after((e) => e.type === 'verdict' && !e.passed).busy).toEqual({ [ORCHESTRATOR]: 'reviewing' });

  // The huddle ends before the answer is written: the orchestrator is still at work.
  expect(after((e) => e.type === 'leave').busy).toEqual({ [ORCHESTRATOR]: 'writing the answer' });

  const answered = story.findIndex((s) => s.ev.type === 'answer');
  for (const s of story.slice(0, answered)) {
    if (s.ev.type === 'join' || s.ev.type === 'assign' || s.ev.type === 'note') continue; // the orchestrator's assign turn sends no event of its own
    expect(Object.keys(s.busy).length, `nobody busy after ${s.ev.type}`).toBeGreaterThan(0);
    expect(s.now).not.toBeNull();
  }
  expect(story[answered].busy).toEqual({});
  expect(story[answered].now).toBeNull();
});

test('a translator that fails leaves mid-question, and the others carry on', () => {
  const story = play([
    { type: 'started', questionId: 'q' },
    { type: 'join', agentId: 'a', how: 'volunteered' },
    { type: 'join', agentId: 'b', how: 'volunteered' },
    { type: 'reading', agentId: 'a' },
    { type: 'reading', agentId: 'b' },
    { type: 'leave', agentIds: ['a'] },
    { type: 'say', agentId: 'b', text: 'found it' },
  ]);
  expect(story[4].busy).toEqual({ a: 'reading', b: 'reading' });
  expect(story[5].busy).toEqual({ b: 'reading' });
  expect(story[6].busy).toEqual({ [ORCHESTRATOR]: 'reviewing' });
});
