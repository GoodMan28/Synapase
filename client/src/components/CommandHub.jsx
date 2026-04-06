import { useState, useRef, useEffect } from 'react';

export default function CommandHub({ onSubmit, disabled = false }) {
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 800);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!query.trim() || disabled) return;
    onSubmit(query.trim());
  };

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      handleSubmit(e);
    }
  };

  return (
    <div className="command-hub">
      <div className="command-hub__branding">
        <span className="command-hub__logo">PROJECT-75A</span>
      </div>

      <h1 className="command-hub__title">
        Multi-Agent Intelligence
      </h1>
      <p className="command-hub__subtitle">
        Decompose. Execute. Synthesize.
      </p>

      <form onSubmit={handleSubmit} className="command-hub__form">
        <div className={`command-hub__input-wrapper ${isFocused ? 'focused' : ''} ${disabled ? 'disabled' : ''}`}>
          <svg className="command-hub__search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            className="command-hub__input"
            placeholder="What would you like to research..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            id="command-input"
            autoComplete="off"
            spellCheck="false"
          />
          <button
            type="submit"
            className="command-hub__submit"
            disabled={!query.trim() || disabled}
            aria-label="Submit research query"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        <div className="command-hub__meta">
          <span className="command-hub__shortcut">
            <kbd>Ctrl</kbd> + <kbd>Enter</kbd>
          </span>
          <span className="command-hub__powered">
            <span className="command-hub__dot" />
            Powered by Gemini + LangGraph
          </span>
        </div>
      </form>
    </div>
  );
}
