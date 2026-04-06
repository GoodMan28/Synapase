import { useState, useCallback, useRef } from 'react';
import './App.css';
import RippleBackground from './components/RippleBackground';
import WormholeBackground from './components/WormholeBackground';
import CommandHub from './components/CommandHub';
import ProcessTracker from './components/ProcessTracker';
import OutputTerminal from './components/OutputTerminal';

const API_BASE = '/api';

function App() {
  const [appState, setAppState] = useState('idle'); // idle | thinking | complete | error
  const [activeNode, setActiveNode] = useState(null);
  const [completedNodes, setCompletedNodes] = useState([]);
  const [outputContent, setOutputContent] = useState('');
  const [researchId, setResearchId] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const abortRef = useRef(null);
  const activeNodeRef = useRef(null);

  const startResearch = useCallback(async (query) => {
    // Reset state
    setAppState('thinking');
    setOutputContent('');
    setActiveNode(null);
    setCompletedNodes([]);
    setResearchId(null);
    setErrorMessage('');
    activeNodeRef.current = null;

    // Abort any previous request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_BASE}/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: query }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        let eventType = null;
        let dataLines = [];

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            // If we have a pending event, process it first
            if (eventType && dataLines.length > 0) {
              processSSEEvent(eventType, dataLines.join('\n'));
            }
            eventType = line.slice(7).trim();
            dataLines = [];
          } else if (line.startsWith('data: ')) {
            dataLines.push(line.slice(6));
          } else if (line === '' && eventType) {
            // Empty line = end of event
            if (dataLines.length > 0) {
              processSSEEvent(eventType, dataLines.join('\n'));
            }
            eventType = null;
            dataLines = [];
          }
        }

        // Handle any remaining event in buffer
        if (eventType && dataLines.length > 0) {
          // Don't process yet — wait for the empty line delimiter
        }
      }

      // Process any final buffered event
      if (buffer.trim()) {
        const remainingLines = buffer.split('\n');
        let eventType = null;
        let dataLines = [];
        for (const line of remainingLines) {
          if (line.startsWith('event: ')) {
            if (eventType && dataLines.length > 0) {
              processSSEEvent(eventType, dataLines.join('\n'));
            }
            eventType = line.slice(7).trim();
            dataLines = [];
          } else if (line.startsWith('data: ')) {
            dataLines.push(line.slice(6));
          }
        }
        if (eventType && dataLines.length > 0) {
          processSSEEvent(eventType, dataLines.join('\n'));
        }
      }

    } catch (err) {
      if (err.name === 'AbortError') return;
      console.error('Research stream error:', err);
      setAppState('error');
      setErrorMessage(err.message || 'An unexpected error occurred.');
    }
  }, []);

  const processSSEEvent = useCallback((eventType, dataStr) => {
    let data;
    try {
      data = JSON.parse(dataStr);
    } catch {
      console.warn('Failed to parse SSE data:', dataStr);
      return;
    }

    switch (eventType) {
      case 'START_THINKING':
        setAppState('thinking');
        setResearchId(data.research_id || null);
        break;

      case 'AGENT_ACTIVE':
        // When a new node becomes active, mark the previous one as completed
        if (data.node) {
          if (activeNodeRef.current && activeNodeRef.current !== data.node) {
            const prev = activeNodeRef.current;
            setCompletedNodes(nodes => nodes.includes(prev) ? nodes : [...nodes, prev]);
          }
          activeNodeRef.current = data.node;
          setActiveNode(data.node);
        }
        break;

      case 'SECTION_COMPLETE':
        // Keep parallel node active during section completion
        setActiveNode('parallel');
        activeNodeRef.current = 'parallel';
        break;

      case 'AUDITOR_REVISION':
        // Mark compiler done, flash auditor, then switch back to parallel for revision
        setCompletedNodes(nodes => nodes.includes('compiler') ? nodes : [...nodes, 'compiler']);
        setActiveNode('auditor');
        activeNodeRef.current = 'auditor';
        setTimeout(() => {
          setCompletedNodes(nodes => nodes.includes('auditor') ? nodes : [...nodes, 'auditor']);
          setActiveNode('parallel');
          activeNodeRef.current = 'parallel';
        }, 1500);
        break;

      case 'FINAL_DOC':
        // Mark the last active node (auditor) as complete too
        setCompletedNodes(['frontier', 'parallel', 'compiler', 'auditor']);
        setActiveNode(null);
        activeNodeRef.current = null;
        setAppState('complete');
        setOutputContent(data.document || '');
        if (data.research_id) {
          setResearchId(data.research_id);
        }
        break;

      case 'ERROR':
        setActiveNode(null);
        setAppState('error');
        setErrorMessage(data.message || 'Pipeline error occurred.');
        break;

      default:
        console.log('Unknown SSE event:', eventType, data);
    }
  }, []);

  const handleReset = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setAppState('idle');
    setActiveNode(null);
    setCompletedNodes([]);
    setOutputContent('');
    setResearchId(null);
    setErrorMessage('');
    activeNodeRef.current = null;
  }, []);

  const handleDownloadPDF = useCallback(async () => {
    if (!researchId) return;
    try {
      const response = await fetch(`${API_BASE}/research/${researchId}/pdf`);
      if (!response.ok) throw new Error('PDF download failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `project75a_research_${researchId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF download error:', err);
    }
  }, [researchId]);

  return (
    <>
      {/* Background Animations */}
      <RippleBackground active={appState === 'idle'} />
      <WormholeBackground active={appState === 'thinking'} />

      {/* Main Content */}
      <main className="app-main">
        {/* Navigation */}
        <nav className="app-nav">
          <button className="app-nav__logo" onClick={handleReset}>
            <span className="app-nav__logo-mark">◇</span>
            <span className="app-nav__logo-text">PROJECT-75A</span>
          </button>
          <div className="app-nav__right">
            <span className="app-nav__status">
              <span className={`app-nav__status-dot ${appState}`} />
              {appState === 'idle' && 'Ready'}
              {appState === 'thinking' && 'Processing'}
              {appState === 'complete' && 'Complete'}
              {appState === 'error' && 'Error'}
            </span>
          </div>
        </nav>

        {/* Hero Section */}
        <div className={`hero-section ${appState !== 'idle' ? 'collapsed' : ''}`}>
          <CommandHub
            onSubmit={startResearch}
            disabled={appState === 'thinking'}
          />
        </div>

        {/* Error Display */}
        {appState === 'error' && (
          <div className="error-banner" id="error-banner">
            <div className="error-banner__icon">⚠</div>
            <div className="error-banner__content">
              <strong>Pipeline Error</strong>
              <p>{errorMessage}</p>
            </div>
            <button className="error-banner__retry" onClick={handleReset}>
              Reset
            </button>
          </div>
        )}

        {/* Process Tracker */}
        <ProcessTracker
          status={appState === 'error' ? 'idle' : appState}
          activeNode={activeNode}
          completedNodes={completedNodes}
        />

        {/* Output Terminal */}
        <OutputTerminal
          content={outputContent}
          visible={appState === 'complete'}
        />

        {/* PDF Download Button */}
        {appState === 'complete' && researchId && (
          <div className="pdf-download-wrapper">
            <button
              className="pdf-download-btn"
              onClick={handleDownloadPDF}
              id="download-pdf-btn"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Export PDF
            </button>
          </div>
        )}

        {/* Footer */}
        <footer className="app-footer">
          <span>Multi-Agent Research Engine</span>
          <span className="app-footer__sep">·</span>
          <span>v0.75a</span>
        </footer>
      </main>
    </>
  );
}

export default App;
