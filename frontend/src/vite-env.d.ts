/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The real backend's origin, for example http://127.0.0.1:8321. Unset: the in-memory mock. */
  readonly VITE_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
