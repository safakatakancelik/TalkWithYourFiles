import { mockBackend } from './mock';
import type { Backend } from './types';

// The only place a backend is chosen. Swap this line to connect a real one.
export const backend: Backend = mockBackend;
