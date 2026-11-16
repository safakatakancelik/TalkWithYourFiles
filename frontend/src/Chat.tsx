import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { ChatMsg, Citation } from './backend/types';

export type ChatMode = 'bar' | 'half' | 'full';

/** Turns "[1]" markers in the text into clickable citation buttons. */
export function withCitations(text: string, citations: Citation[] | undefined, onCite: (c: Citation) => void): ReactNode[] {
  return text.split(/(\[\d+\])/).map((part, i) => {
    const c = citations?.find((x) => `[${x.n}]` === part);
    return c ? <button key={i} className="cite" title={c.location} onClick={() => onCite(c)}>{c.n}</button> : part;
  });
}

interface Props {
  mode: ChatMode;
  messages: ChatMsg[];
  busy: boolean;
  hasFiles: boolean;
  onSend: (text: string) => void;
  onCite: (c: Citation) => void;
}

export function Chat({ mode, messages, busy, hasFiles, onSend, onCite }: Props) {
  const [text, setText] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [messages.length, last?.status, last?.text]);

  const submit = () => {
    if (!text.trim() || busy) return;
    onSend(text.trim());
    setText('');
  };

  return (
    <section className="chat">
      {mode !== 'bar' && (
        <div className="messages">
          {messages.length === 0 && (
            <p className="muted center">
              {hasFiles ? 'Ask a question about your files.' : 'Upload files in the explorer (E), then ask a question about them.'}
            </p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role}`}>
              {m.error ? <span className="error-text">{m.error}</span> : m.pending ? <span className="status"><i className="dot" />{m.status}</span> : (
                <>
                  {m.placeholder && <span className="tag">Simulated</span>}
                  {m.text.split('\n\n').map((p, i) => <p key={i}>{withCitations(p, m.citations, onCite)}</p>)}
                  {m.unverified && m.unverified.length > 0 && (
                    <div className="unverified">
                      <strong>Could not be verified</strong>
                      <ul>{m.unverified.map((u, i) => <li key={i}>{u.text} <span className="muted">{u.reason}</span></li>)}</ul>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
          <div ref={end} />
        </div>
      )}
      <form className="input" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {mode === 'bar' && last?.pending && <span className="status"><i className="dot" />{last.status}</span>}
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about your files" aria-label="Your question" />
        <button className="primary" disabled={busy || !text.trim()}>Send</button>
      </form>
    </section>
  );
}
