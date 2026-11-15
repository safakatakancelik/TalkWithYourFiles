import { ORCHESTRATOR } from '../backend/types';
import type { Agent, AgentEvent, ChatMsg, Citation, ContextMap, FileItem, Note, Session } from '../backend/types';

// The demo scenario: a made-up company, six dummy files, a pool of five translators and a scripted huddle.
// It is plain data, so it can later be replayed against a real backend as a test case.

export const DEMO_WORKSPACE = { id: 'demo', name: 'Harbor Coffee Roasters (demo)' };

export const DEMO_QUESTION =
  'Our coffee supplier is raising prices in January. Can we keep our current prices and still hit our margin target?';

const file = (id: string, name: string, type: FileItem['type'], sizeKb: number): FileItem => ({
  id, name, type, sizeKb, uploadedAt: '2026-11-03T09:00:00Z',
});

const files: FileItem[] = [
  file('f-contract', 'supplier-contract-andes.pdf', 'pdf', 412),
  file('f-sales', 'q3-sales-2026.csv', 'csv', 88),
  file('f-board', 'board-notes-2026-10.docx', 'docx', 36),
  file('f-pricing', 'pricing-policy.md', 'md', 9),
  file('f-hr', 'hr-handbook.pdf', 'pdf', 1204),
  file('f-lease', 'office-lease.pdf', 'pdf', 655),
];

// The pool: generic translators plus specialised ones. None of them belongs to a file.
const agents: Agent[] = [
  { id: 'a-t1', name: 'Translator 1', specialty: 'generic' },
  { id: 'a-t2', name: 'Translator 2', specialty: 'generic' },
  { id: 'a-contracts', name: 'Contracts translator', specialty: 'contracts' },
  { id: 'a-finance', name: 'Finance translator', specialty: 'finance' },
  { id: 'a-people', name: 'People translator', specialty: 'people' },
];

const note = (id: string, fileId: string, authorId: string, kind: Note['kind'], text: string, citations: Citation[] = [], createdAt = '2026-11-03T09:05:00Z'): Note => ({
  id, fileId, authorId, kind, text, citations, createdAt, weight: 'normal',
});

// Notes written before the demo starts, when the files were first read.
const notes: Note[] = [
  note('n-contract', 'f-contract', 'a-contracts', 'summary',
    'Supply contract with Andes Green Coffee. Green coffee at $6.40 per kg through December 2026, with an 8% increase from 1 January 2027.'),
  note('n-sales', 'f-sales', 'a-finance', 'summary',
    'Q3 2026 sales by channel. 5,150 kg sold at an average of $29.00 per kg. Cost of goods $13.05 per kg, of which green coffee is $7.60.'),
  note('n-board', 'f-board', 'a-t1', 'summary',
    'October 2026 board meeting. Retail prices held until March 2027. Gross margin target set at 55%.'),
  note('n-pricing', 'f-pricing', 'a-t2', 'summary',
    'Pricing policy. Prices must be reviewed when cost of goods moves more than 5%. Wholesale discounts are capped at 15%.'),
  note('n-hr', 'f-hr', 'a-people', 'summary', 'Employee handbook: leave, working hours, conduct and benefits.'),
  note('n-lease', 'f-lease', 'a-contracts', 'summary', 'Lease for the roastery and office at 14 Quay Street, running to 2029.'),
];

const map: ContextMap = {
  nodes: [
    ...files.map((f) => ({ id: f.id, label: f.name, kind: 'file' as const })),
    { id: 'e-andes', label: 'Andes Green Coffee', kind: 'entity' },
    { id: 'e-margin', label: 'Gross margin target 55%', kind: 'entity' },
    { id: 'e-prices', label: 'Retail prices', kind: 'entity' },
    { id: 'e-quay', label: '14 Quay Street', kind: 'entity' },
    { id: 'e-staff', label: 'Staff', kind: 'entity' },
  ],
  links: [
    { from: 'f-contract', to: 'e-andes' },
    { from: 'f-sales', to: 'e-margin' },
    { from: 'f-sales', to: 'e-prices' },
    { from: 'f-board', to: 'e-margin' },
    { from: 'f-board', to: 'e-prices' },
    { from: 'f-pricing', to: 'e-prices' },
    { from: 'f-lease', to: 'e-quay' },
    { from: 'f-hr', to: 'e-staff' },
    { from: 'f-board', to: 'e-staff' },
  ],
};

const sessions: Session[] = [
  { id: 's-lease', title: 'When does the office lease end?', updatedAt: '2026-11-09T14:20:00Z', messageCount: 2 },
];

const cite = (n: number, fileId: string, agentId: string, location: string, passage: string, quote: string): Citation => ({
  n, fileId, agentId, location, passage, quote,
});

const messages: Record<string, ChatMsg[]> = {
  's-lease': [
    { id: 'm1', role: 'user', text: 'When does the office lease end?' },
    {
      id: 'm2', role: 'assistant', text: 'The lease for 14 Quay Street runs until 30 June 2029 [1].',
      citations: [cite(1, 'f-lease', 'a-contracts', 'Section 2, Term',
        'The Term shall commence on 1 July 2024 and shall expire on 30 June 2029 unless terminated earlier under Section 11.',
        'shall expire on 30 June 2029')],
    },
  ],
};

export const demoWorkspace = { files, agents, notes, sessions, map, messages };

const c1 = cite(1, 'f-contract', 'a-contracts', 'Clause 4.2, Price adjustment',
  'The Price shall be USD 6.40 per kilogram until 31 December 2026. From 1 January 2027 the Price shall increase by eight percent (8%) to USD 6.91 per kilogram.',
  'From 1 January 2027 the Price shall increase by eight percent (8%)');
const c2 = cite(2, 'f-sales', 'a-finance', 'Summary row, Q3 2026',
  'total_kg=5150, avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60, gross_margin=55.0%',
  'avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60');
const c3 = cite(3, 'f-board', 'a-t1', 'Item 3, Pricing and margin',
  'The board agreed to hold retail prices at current levels until the March 2027 meeting. The gross margin target for the financial year remains 55%.',
  'hold retail prices at current levels until the March 2027 meeting');
const c4 = cite(4, 'f-pricing', 'a-t2', 'Section 2, Review triggers',
  'A price review is required whenever cost of goods moves by more than 5% in either direction. The review must be presented to the board within 30 days.',
  'A price review is required whenever cost of goods moves by more than 5%');

export interface ScriptStep {
  /** Milliseconds to wait before the event, at normal speed. */
  delay: number;
  event: AgentEvent;
}

const step = (delay: number, event: AgentEvent): ScriptStep => ({ delay, event });

/** An agent says something about its file, then stores it as a note with the same citation. */
const finding = (delay: number, id: string, c: Citation, text: string): ScriptStep[] => [
  step(delay, { type: 'say', agentId: c.agentId, citations: [c], text }),
  step(500, { type: 'note', note: note(id, c.fileId, c.agentId, 'finding', text, [c], '2026-11-15T10:00:00Z') }),
];

export const demoScript: ScriptStep[] = [
  step(900, { type: 'status', text: 'The chat agent passed your question to the orchestrator' }),
  step(1200, {
    type: 'broadcast', to: agents.map((a) => a.id),
    text: 'Who can take supplier price changes, our current prices, or our margin target?',
  }),
  step(1400, { type: 'join', agentId: 'a-contracts', how: 'volunteered' }),
  step(700, { type: 'join', agentId: 'a-finance', how: 'volunteered' }),
  step(700, { type: 'join', agentId: 'a-t1', how: 'volunteered' }),
  step(1000, { type: 'assign', agentId: 'a-contracts', fileId: 'f-contract' }),
  step(500, { type: 'assign', agentId: 'a-finance', fileId: 'f-sales' }),
  step(500, { type: 'assign', agentId: 'a-t1', fileId: 'f-board' }),
  step(1000, { type: 'reading', agentId: 'a-contracts' }),
  ...finding(1500, 'n-find-1', c1, 'Clause 4.2: the price rises 8% on 1 January 2027, from $6.40 to $6.91 per kg.'),
  step(1800, { type: 'reading', agentId: 'a-finance' }),
  ...finding(1500, 'n-find-2', c2, 'Q3: average price $29.00 per kg, cost of goods $13.05, of which green coffee is $7.60. Margin is 55.0%.'),
  ...finding(2200, 'n-find-3', c3, 'October board: retail prices are held until March 2027, and the margin target stays at 55%.'),
  step(2200, { type: 'say', agentId: ORCHESTRATOR,
    text: 'A cost change this size may trigger a price review. Translator 2, please join and check the pricing policy.' }),
  step(1300, { type: 'join', agentId: 'a-t2', how: 'called' }),
  step(600, { type: 'assign', agentId: 'a-t2', fileId: 'f-pricing' }),
  step(900, { type: 'reading', agentId: 'a-t2' }),
  ...finding(1500, 'n-find-4', c4, 'Section 2: a review is required when cost of goods moves more than 5%. An 8% rise on green coffee qualifies.'),
  step(2200, { type: 'say', agentId: 'a-finance',
    text: 'Using the Contracts translator\'s note: with green coffee up 8%, cost of goods becomes $13.66 per kg. At $29.00 the margin falls to 52.9%.' }),
  step(2400, { type: 'say', agentId: ORCHESTRATOR,
    text: 'Settled: the margin target is missed unless prices rise about 4.7%. That conflicts with the price hold.' }),
  step(2200, { type: 'leave', agentIds: ['a-contracts', 'a-finance', 'a-t1', 'a-t2'] }),
  step(600, { type: 'status', text: 'The orchestrator returned the findings. Writing the answer' }),
  step(400, {
    type: 'context',
    nodes: [{ id: 'e-increase', label: 'January 2027 price increase', kind: 'entity' }],
    links: [
      { from: 'f-contract', to: 'e-increase' },
      { from: 'f-pricing', to: 'e-increase' },
      { from: 'f-board', to: 'e-increase' },
    ],
  }),
  step(1200, {
    type: 'answer', citations: [c1, c2, c3, c4],
    text:
      'Not without changing something. From 1 January 2027, Andes Green Coffee raises its price by 8% [1]. ' +
      'At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9% [2], which is below the board\'s 55% target [3].\n\n' +
      'The board also decided to hold retail prices until March 2027 [3], but the pricing policy requires a price review ' +
      'when cost of goods moves more than 5% [4]. To stay at 55% you would need a price rise of about 4.7%, to roughly $30.36 per kg. ' +
      'The price hold and the margin target cannot both be kept, so this needs a board decision.',
  }),
];
