import { useState, useCallback } from 'react';
import './App.css';
import RippleBackground from './components/RippleBackground';
import WormholeBackground from './components/WormholeBackground';
import CommandHub from './components/CommandHub';
import ProcessTracker from './components/ProcessTracker';
import OutputTerminal from './components/OutputTerminal';

// Mock research output for demonstration
const MOCK_OUTPUT = `# Quantum Computing in Drug Discovery

## Executive Summary

Quantum computing is poised to **revolutionize pharmaceutical research** by enabling molecular simulations that are computationally intractable for classical systems. This report synthesizes findings from 5 parallel research agents.

## Key Findings

### 1. Molecular Simulation Capabilities
- Quantum computers can simulate molecular interactions at the **atomic level** with exponential speedup
- Variational Quantum Eigensolver (VQE) algorithms show promise for protein folding predictions
- Current estimates suggest a \`10,000x\` improvement in binding affinity calculations

### 2. Current State of the Art

| Company | Qubits | Approach | Drug Pipeline |
|---------|--------|----------|---------------|
| IBM | 1,121 | Superconducting | Lithium compound screening |
| Google | 72 | Superconducting | Molecular dynamics |
| IonQ | 32 | Trapped Ion | Enzyme catalysis |

### 3. Challenges & Limitations

> **Note:** Current quantum hardware operates in the NISQ (Noisy Intermediate-Scale Quantum) era, limiting practical applications.

- **Decoherence**: Quantum states are fragile and collapse within microseconds
- **Error rates**: Current quantum computers have error rates of ~0.1-1%
- **Scalability**: True quantum advantage requires 10,000+ logical qubits

### 4. Projected Timeline

1. **2025-2027**: Hybrid quantum-classical algorithms for lead optimization
2. **2028-2030**: Full quantum simulation of small drug molecules
3. **2031+**: Large-scale protein-drug interaction modeling

## Methodology

This research was compiled by the **Project-75A Multi-Agent System**:

\`\`\`
Frontier Agent   → Query decomposition into 5 sub-prompts
Parallel Nodes   → Concurrent Gemini API execution
Compiler         → Cross-reference & synthesis
Auditor Loop     → Fact-checking & consistency validation (2 iterations)
\`\`\`

## Sources

- Nature Quantum Information, Vol. 9, 2024
- IBM Quantum Research Blog
- Google AI Quantum Team Publications
- arXiv:2401.xxxxx — "Quantum Advantage in Molecular Dynamics"
`;

function App() {
  const [appState, setAppState] = useState('idle'); // idle | thinking | complete
  const [activeNode, setActiveNode] = useState(null);
  const [outputContent, setOutputContent] = useState('');

  const simulateResearch = useCallback((query) => {
    setAppState('thinking');
    setOutputContent('');

    // Simulate the agent pipeline
    const nodes = ['frontier', 'parallel', 'compiler', 'auditor'];
    let nodeIndex = 0;

    const nodeInterval = setInterval(() => {
      if (nodeIndex < nodes.length) {
        setActiveNode(nodes[nodeIndex]);
        nodeIndex++;
      } else {
        clearInterval(nodeInterval);
      }
    }, 1200);

    // Complete after pipeline finishes
    setTimeout(() => {
      clearInterval(nodeInterval);
      setActiveNode(null);
      setAppState('complete');
      setOutputContent(MOCK_OUTPUT);
    }, 6500);
  }, []);

  const handleReset = useCallback(() => {
    setAppState('idle');
    setActiveNode(null);
    setOutputContent('');
  }, []);

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
            </span>
          </div>
        </nav>

        {/* Hero Section */}
        <div className={`hero-section ${appState !== 'idle' ? 'collapsed' : ''}`}>
          <CommandHub
            onSubmit={simulateResearch}
            disabled={appState === 'thinking'}
          />
        </div>

        {/* Process Tracker */}
        <ProcessTracker
          status={appState}
          activeNode={activeNode}
        />

        {/* Output Terminal */}
        <OutputTerminal
          content={outputContent}
          visible={appState === 'complete'}
        />

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
