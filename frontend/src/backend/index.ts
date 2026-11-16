import { httpBackend } from './http';
import { mockBackend } from './mock';
import { withDemo } from './router';
import type { Backend } from './types';

// The only place a backend is chosen. With VITE_BACKEND_URL set, the real backend serves every workspace
// except the demo, which always plays the mock's scripted story.
const url = import.meta.env.VITE_BACKEND_URL;
export const backend: Backend = url ? withDemo(httpBackend(url), mockBackend) : mockBackend;
