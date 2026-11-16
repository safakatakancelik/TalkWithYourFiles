import { ORCHESTRATOR, VERIFIER } from './backend/types';
import type { AgentEvent } from './backend/types';
import type { Huddle } from './Stage';

/**
 * The story of a question as the stage tells it: who is doing something right now, the one line saying what is
 * happening, and the messages in flight between agents. The stream reports results, not turns starting, but the
 * backend always runs a question in the same order, so each event says who works next:
 *
 *   started    the orchestrator plans
 *   broadcast  the translators it asked decide whether to help (then it assigns files, which sends no event)
 *   reading    that translator reads its files
 *   say        a translator reports back; when the last one has, the orchestrator reviews
 *   verify     the verifier checks the claims; its verdict sends the orchestrator back to review or to the answer
 *   leave      the huddle is over and the answer is written, unless some members stay
 */
export type Story = Pick<Huddle, 'busy' | 'now' | 'flights'>;

/** How many messages in flight are kept. Each is drawn once, when it first appears. */
const FLIGHTS_KEPT = 24;

const count = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;
const list = (names: string[]) => (names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`);
const isTranslator = (id: string) => id !== ORCHESTRATOR && id !== VERIFIER;

export function tell(h: Huddle, ev: AgentEvent, nameOf: (id: string) => string, fileName: (id: string) => string, at = Date.now()): Story {
  const { busy, now, flights } = h;
  const line = (text: string) => ({ text, since: at });
  const fly = (pairs: [string, string][]) => {
    let id = flights.at(-1)?.id ?? 0;
    return [...flights, ...pairs.map(([from, to]) => ({ id: ++id, from, to }))].slice(-FLIGHTS_KEPT);
  };
  const reviewing = { busy: { [ORCHESTRATOR]: 'reviewing' }, now: line('The orchestrator is reviewing what the translators found') };

  switch (ev.type) {
    case 'started':
      return { busy: { [ORCHESTRATOR]: 'planning' }, now: line('The orchestrator is reading your question and planning who to ask'), flights };
    case 'broadcast':
      return {
        busy: Object.fromEntries(ev.to.map((id) => [id, 'deciding'])),
        now: line(`The orchestrator asked ${count(ev.to.length, 'translator')} who can help`),
        flights: fly(ev.to.map((id) => [ORCHESTRATOR, id])),
      };
    case 'join': {
      // Joins come once the orchestrator has picked its team: nobody is deciding any more.
      const rest = Object.fromEntries(Object.entries(busy).filter(([, doing]) => doing !== 'deciding'));
      const called = ev.how === 'called';
      return {
        busy: rest,
        now: line(`${nameOf(ev.agentId)} ${called ? 'was called into' : 'joined'} the huddle`),
        flights: called ? fly([[ORCHESTRATOR, ev.agentId]]) : flights,
      };
    }
    case 'assign':
      return { busy, now: line(`${nameOf(ev.agentId)} was given ${fileName(ev.fileId)}`), flights };
    case 'reading': {
      const file = h.working[ev.agentId];
      const { [ORCHESTRATOR]: _, ...rest } = busy;
      const next = { ...rest, [ev.agentId]: file ? `reading ${fileName(file)}` : 'reading' };
      const readers = Object.keys(next).filter(isTranslator);
      return {
        busy: next,
        now: line(readers.length > 1
          ? `${list(readers.map(nameOf))} are reading their files`
          : `${nameOf(ev.agentId)} is reading ${file ? fileName(file) : 'its files'}`),
        flights,
      };
    }
    case 'say': {
      if (ev.agentId === ORCHESTRATOR) {
        return { busy: { [ORCHESTRATOR]: 'deciding the next step' }, now: line('The orchestrator is deciding the next step'), flights };
      }
      const { [ev.agentId]: _, ...rest } = busy;
      const left = Object.keys(rest).filter(isTranslator);
      const back = fly([[ev.agentId, ORCHESTRATOR]]);
      if (left.length) return { busy: rest, now: line(`${nameOf(ev.agentId)} reported back. Waiting for ${list(left.map(nameOf))}`), flights: back };
      return { ...reviewing, flights: back };
    }
    case 'verify':
      return {
        busy: { [VERIFIER]: 'checking claims' },
        now: line(`The verifier is checking ${count(ev.claims.length, 'claim')} against the files`),
        flights: fly([[ORCHESTRATOR, VERIFIER]]),
      };
    case 'verdict':
      return {
        busy: { [ORCHESTRATOR]: ev.passed ? 'wrapping up' : 'reviewing' },
        now: line(ev.passed ? 'Every claim checked out' : 'Some claims could not be verified'),
        flights: fly([[VERIFIER, ORCHESTRATOR]]),
      };
    case 'rehuddle':
      return { busy: { [ORCHESTRATOR]: 'reviewing' }, now: line(`Round ${ev.round}: the orchestrator sends the translators back to check`), flights };
    case 'leave': {
      const staying = h.members.filter((m) => !ev.agentIds.includes(m));
      if (!staying.length) return { busy: { [ORCHESTRATOR]: 'writing the answer' }, now: line('The huddle is over. The answer is being written'), flights };
      // A translator whose turn failed leaves mid-question; the others carry on.
      const rest = Object.fromEntries(Object.entries(busy).filter(([id]) => !ev.agentIds.includes(id)));
      return {
        busy: Object.keys(rest).length ? rest : reviewing.busy,
        now: line(`${list(ev.agentIds.map(nameOf))} left the huddle`),
        flights,
      };
    }
    case 'answer':
    case 'error':
    case 'cancelled':
      return { busy: {}, now: null, flights };
    default:
      return { busy, now, flights };
  }
}
