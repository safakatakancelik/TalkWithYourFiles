import { expect, test } from 'vitest';
import { mockBackend } from './mock';
import { withDemo } from './router';
import type { Backend } from './types';

function recorder(): { backend: Backend; calls: string[] } {
  const calls: string[] = [];
  const backend = new Proxy({} as Backend, {
    get: (_, name: string) => async (...args: unknown[]) => {
      calls.push(`${name}(${args.filter((a) => typeof a === 'string').join(',')})`);
      return name === 'listWorkspaces' ? [{ id: 'ws_1', name: 'Mine' }] : [];
    },
  });
  return { backend, calls };
}

test('the demo workspace goes to the mock and every other to the real backend', async () => {
  const real = recorder();
  const routed = withDemo(real.backend, mockBackend);
  expect((await routed.listWorkspaces()).map((w) => w.id)).toEqual(['ws_1', 'demo']);
  expect((await routed.listFiles('demo')).map((f) => f.id)).toContain('f-contract');
  await routed.listFiles('ws_1');
  await routed.createWorkspace('New');
  await routed.deleteNote('ws_1', 'n1');
  expect(real.calls).toEqual(['listWorkspaces()', 'listFiles(ws_1)', 'createWorkspace(New)', 'deleteNote(ws_1,n1)']);
});
