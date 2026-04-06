import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function OutputTerminal({ content = '', visible = false }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // silently fail
    }
  };

  if (!visible && !content) return null;

  return (
    <div className={`output-terminal ${visible ? 'visible' : ''}`}>
      <div className="output-terminal__header">
        <div className="output-terminal__title-row">
          <div className="output-terminal__dots">
            <span className="dot red" />
            <span className="dot amber" />
            <span className="dot green" />
          </div>
          <span className="output-terminal__title">Research Output</span>
        </div>
        <div className="output-terminal__actions">
          <button
            className="output-terminal__copy"
            onClick={handleCopy}
            aria-label="Copy output"
          >
            {copied ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
          </button>
        </div>
      </div>
      <div className="output-terminal__content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
            h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
            h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
            p: ({ children }) => <p className="md-p">{children}</p>,
            ul: ({ children }) => <ul className="md-ul">{children}</ul>,
            ol: ({ children }) => <ol className="md-ol">{children}</ol>,
            li: ({ children }) => <li className="md-li">{children}</li>,
            code: ({ inline, className, children }) => {
              if (inline) {
                return <code className="md-code-inline">{children}</code>;
              }
              return (
                <pre className="md-code-block">
                  <code className={className}>{children}</code>
                </pre>
              );
            },
            blockquote: ({ children }) => <blockquote className="md-blockquote">{children}</blockquote>,
            table: ({ children }) => (
              <div className="md-table-wrapper">
                <table className="md-table">{children}</table>
              </div>
            ),
            strong: ({ children }) => <strong className="md-strong">{children}</strong>,
            a: ({ href, children }) => (
              <a href={href} className="md-link" target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
