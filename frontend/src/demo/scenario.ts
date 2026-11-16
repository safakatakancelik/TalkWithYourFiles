import { ORCHESTRATOR } from '../backend/types';
import type { Agent, AgentEvent, ChatMsg, Citation, Claim, ContextMap, FileItem, Note, Session, Verdict } from '../backend/types';

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

const cite = (n: number, fileId: string, agentId: string, location: string, passage: string, quote: string): Citation => ({
  n, fileId, agentId, location, passage, quote,
});

// The paragraphs the quotes come from, as the backend extracts them (10-demo-scenario.md section 2).
const P_CONTRACT = 'Clause 4.2, Price adjustment. The Price shall be USD 6.40 per kilogram until 31 December 2026. From 1 January 2027 the Price shall increase by eight percent (8%) to USD 6.91 per kilogram.';
const P_SALES = 'channel=Total Q3 2026, total_kg=5150, avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60, gross_margin=55.0%';
const P_BOARD = 'The board agreed to hold retail prices at current levels until the March 2027 meeting. The gross margin target for the financial year remains 55%.';
const P_PRICING = 'A price review is required whenever cost of goods moves by more than 5% in either direction. The review must be presented to the board within 30 days.';

// Notes written before the demo starts, when the files were first read. Every summary is cited, numbered from 1 within its note.
const notes: Note[] = [
  note('n-contract', 'f-contract', 'a-contracts', 'summary',
    'Supply contract with Andes Green Coffee. Green coffee at $6.40 per kg through December 2026, with an 8% increase from 1 January 2027.', [
      cite(1, 'f-contract', 'a-contracts', 'Clause 4.2, Price adjustment', P_CONTRACT, 'The Price shall be USD 6.40 per kilogram until 31 December 2026'),
      cite(2, 'f-contract', 'a-contracts', 'Clause 4.2, Price adjustment', P_CONTRACT, 'From 1 January 2027 the Price shall increase by eight percent (8%)'),
    ]),
  note('n-sales', 'f-sales', 'a-finance', 'summary',
    'Q3 2026 sales by channel. 5,150 kg sold at an average of $29.00 per kg. Cost of goods $13.05 per kg, of which green coffee is $7.60.', [
      cite(1, 'f-sales', 'a-finance', 'Row 4', P_SALES, 'total_kg=5150, avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60'),
    ]),
  note('n-board', 'f-board', 'a-t1', 'summary',
    'October 2026 board meeting. Retail prices held until March 2027. Gross margin target set at 55%.', [
      cite(1, 'f-board', 'a-t1', 'Item 3, Pricing and margin', P_BOARD, 'hold retail prices at current levels until the March 2027 meeting'),
      cite(2, 'f-board', 'a-t1', 'Item 3, Pricing and margin', P_BOARD, 'The gross margin target for the financial year remains 55%'),
    ]),
  note('n-pricing', 'f-pricing', 'a-t2', 'summary',
    'Pricing policy. Prices must be reviewed when cost of goods moves more than 5%. Wholesale discounts are capped at 15%.', [
      cite(1, 'f-pricing', 'a-t2', 'Section 2, Review triggers', P_PRICING, 'A price review is required whenever cost of goods moves by more than 5%'),
      cite(2, 'f-pricing', 'a-t2', 'Section 3, Wholesale discounts', 'Wholesale discounts are capped at 15% of list price.', 'Wholesale discounts are capped at 15%'),
    ]),
  note('n-hr', 'f-hr', 'a-people', 'summary', 'Employee handbook: leave, working hours, conduct and benefits.', [
    cite(1, 'f-hr', 'a-people', 'Section 3, Leave', 'Section 3, Leave. Full-time staff receive 25 days of paid leave per year.',
      'Full-time staff receive 25 days of paid leave per year'),
  ]),
  note('n-lease', 'f-lease', 'a-contracts', 'summary', 'Lease for the roastery and office at 14 Quay Street, running to 2029.', [
    cite(1, 'f-lease', 'a-contracts', 'Section 1, Premises',
      'Section 1, Premises. The Landlord lets the roastery and office at 14 Quay Street to the Tenant.', 'roastery and office at 14 Quay Street'),
    cite(2, 'f-lease', 'a-contracts', 'Section 2, Term',
      'Section 2, Term. The Term shall commence on 1 July 2024 and shall expire on 30 June 2029 unless terminated earlier under Section 11.',
      'shall expire on 30 June 2029'),
  ]),
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

const c1 = cite(1, 'f-contract', 'a-contracts', 'Clause 4.2, Price adjustment', P_CONTRACT,
  'From 1 January 2027 the Price shall increase by eight percent (8%)');
const c2 = cite(2, 'f-sales', 'a-finance', 'Row 4', P_SALES,
  'avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60');
// The whole Item 3 paragraph, so that citation 3 supports both halves of claim k3.
const c3 = cite(3, 'f-board', 'a-t1', 'Item 3, Pricing and margin', P_BOARD,
  'hold retail prices at current levels until the March 2027 meeting');
const c4 = cite(4, 'f-pricing', 'a-t2', 'Section 2, Review triggers', P_PRICING,
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

// The claims the verifier checks (10-demo-scenario.md section 4). `citations` are the `n` of c1 to c4.
const claim = (id: string, text: string, citations: number[], derivedFrom?: string[], calculation?: string): Claim => ({
  id, text, kind: derivedFrom ? 'derived' : 'quoted', citations, ...(derivedFrom ? { derivedFrom } : {}), ...(calculation ? { calculation } : {}),
});
const k1 = claim('k1', 'Andes Green Coffee raises its price by 8% from 1 January 2027.', [1]);
const k2 = claim('k2', 'In Q3 2026 the average price was $29.00 per kg, cost of goods was $13.05 per kg, of which green coffee was $7.60, and gross margin was 55.0%.', [2]);
const k3 = claim('k3', 'The board holds retail prices until the March 2027 meeting and keeps the gross margin target at 55%.', [3]);
const k4 = claim('k4', 'The pricing policy requires a price review now, because cost of goods moves by more than 5%.', [4]);
const k5 = claim('k5', 'With green coffee up 8%, cost of goods becomes $13.66 per kg and gross margin at $29.00 falls to 52.9%.', [1, 2], ['k1', 'k2'], '1 - (13.05 + 7.60 * 0.08) / 29.00');
const k6 = claim('k6', 'Keeping a 55% margin needs a price of about $30.35 per kg, a rise of about 4.7%.', [1, 2, 3], ['k1', 'k2', 'k3'], '(13.05 + 7.60 * 0.08) / (1 - 0.55)');
const k4b = claim('k4b', 'The pricing policy requires a price review when cost of goods moves by more than 5%.', [4]);
const k7 = claim('k7', 'Cost of goods rises by about 4.7%, which is below the 5% review trigger.', [1, 2, 4], ['k1', 'k2', 'k4b'], '7.60 * 0.08 / 13.05');
const k8 = claim('k8', 'The price hold and the 55% margin target cannot both be kept.', [1, 2, 3], ['k3', 'k5']);
const supported = (c: Claim, reason = 'The cited passages state it.'): Verdict => ({ claimId: c.id, verdict: 'supported', reason });
const K4_REASON = 'The passage gives the 5% rule. Nothing cited shows that cost of goods moves by more than 5%.';

export const demoScript: ScriptStep[] = [
  step(0, { type: 'started', questionId: 'q-demo' }),
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
  ...finding(1500, 'n-find-4', c4, 'Section 2: a review is required when cost of goods moves more than 5%.'),
  step(1800, { type: 'say', agentId: ORCHESTRATOR, text: 'Finance translator, what does the increase do to our margin?' }),
  step(2200, { type: 'say', agentId: 'a-finance', citations: [c1, c2],
    text: 'Using the Contracts translator\'s note: with green coffee up 8%, cost of goods becomes $13.66 per kg. At $29.00 the margin falls to 52.9%.' }),
  step(2000, { type: 'say', agentId: ORCHESTRATOR, text: 'I think we have an answer. Verifier, please check the claims.' }),
  step(1500, { type: 'verify', round: 1, claims: [k1, k2, k3, k4, k5, k6], citations: [c1, c2, c3, c4] }),
  step(2600, { type: 'verdict', round: 1, passed: false, verdicts: [
    supported(k1), supported(k2), supported(k3), { claimId: 'k4', verdict: 'partly_supported', reason: K4_REASON },
    supported(k5), supported(k6),
  ] }),
  step(1200, { type: 'rehuddle', round: 2, reason: K4_REASON, claimIds: ['k4'] }),
  step(1600, { type: 'say', agentId: ORCHESTRATOR,
    text: 'The verifier found no evidence that cost of goods moves more than 5%. Finance translator, how much does it move?' }),
  step(1800, { type: 'reading', agentId: 'a-finance' }),
  step(1500, { type: 'say', agentId: 'a-finance', citations: [c1, c2],
    text: 'Cost of goods moves from $13.05 to $13.66 per kg, which is 4.7%. That is under the 5% trigger.' }),
  step(500, { type: 'note', note: note('n-find-5', 'f-sales', 'a-finance', 'finding',
    'Cost of goods moves about 4.7%, under the 5% review trigger.', [c2], '2026-11-15T10:05:00Z') }),
  step(2000, { type: 'say', agentId: ORCHESTRATOR,
    text: 'Settled: the margin target is missed unless prices rise about 4.7%, and the policy does not force a review.' }),
  step(1500, { type: 'verify', round: 2, claims: [k1, k2, k3, k5, k6, k4b, k7, k8], citations: [c1, c2, c3, c4] }),
  step(2600, { type: 'verdict', round: 2, passed: true, verdicts: [k1, k2, k3, k5, k6, k4b, k7, k8].map((c) => supported(c)) }),
  step(1200, { type: 'leave', agentIds: ['a-contracts', 'a-finance', 'a-t1', 'a-t2'] }),
  step(600, { type: 'status', text: 'Every claim was verified. Writing the answer' }),
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
      'At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9% [1][2]. ' +
      'That is below the board\'s 55% target [3].\n\n' +
      'The board also decided to hold retail prices until March 2027 [3]. ' +
      'The pricing policy requires a review only when cost of goods moves more than 5% [4]. ' +
      'This change is about 4.7%, so the policy does not force one [1][2][4]. ' +
      'To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7% [1][2][3]. ' +
      'The price hold and the margin target cannot both be kept [1][2][3]. This needs a board decision.',
  }),
];
