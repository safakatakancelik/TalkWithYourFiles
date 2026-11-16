// Fails to compile when the hand-written types in types.ts drift from the types generated from the backend.
import type * as H from './types';
import type * as G from './contract.gen';
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
export const checks: true[] = [
  true as Same<H.Workspace, G.Workspace>, true as Same<H.FileItem, G.FileItem>, true as Same<H.Agent, G.Agent>,
  true as Same<H.Note, G.Note>, true as Same<H.Citation, G.Citation>, true as Same<H.Session, G.Session>,
  true as Same<H.ChatMsg, G.ChatMsg>, true as Same<H.ContextMap, G.ContextMap>, true as Same<H.AgentEvent, G.AgentEvent>,
  true as Same<H.Claim, G.Claim>, true as Same<H.Verdict, G.Verdict>, true as Same<H.Unverified, G.Unverified>,
];
