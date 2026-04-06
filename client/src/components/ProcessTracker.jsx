import { useEffect, useState } from 'react';

const NODES = [
  { id: 'frontier', label: 'Frontier Agent', icon: '◆' },
  { id: 'parallel', label: 'Parallel Nodes ×5', icon: '⬡' },
  { id: 'compiler', label: 'Compiler', icon: '⬢' },
  { id: 'auditor', label: 'Auditor Loop', icon: '↻' },
];

export default function ProcessTracker({ status = 'idle', activeNode = null }) {
  const [animatedNodes, setAnimatedNodes] = useState([]);

  useEffect(() => {
    if (status === 'idle') {
      setAnimatedNodes([]);
      return;
    }

    if (status === 'thinking') {
      // Sequentially activate nodes
      const timers = NODES.map((node, i) =>
        setTimeout(() => {
          setAnimatedNodes(prev => [...prev, node.id]);
        }, i * 1200)
      );
      return () => timers.forEach(clearTimeout);
    }

    if (status === 'complete') {
      setAnimatedNodes(NODES.map(n => n.id));
    }
  }, [status]);

  const getNodeState = (nodeId) => {
    if (status === 'idle') return 'idle';
    if (status === 'complete') return 'complete';
    if (activeNode === nodeId) return 'active';
    if (animatedNodes.includes(nodeId)) return 'activated';
    return 'pending';
  };

  return (
    <div className={`process-tracker ${status !== 'idle' ? 'visible' : ''}`}>
      <div className="process-tracker__label">AGENT PIPELINE</div>
      <div className="process-tracker__flow">
        {NODES.map((node, index) => {
          const state = getNodeState(node.id);
          return (
            <div key={node.id} className="process-tracker__step">
              {index > 0 && (
                <div className={`process-tracker__connector ${state !== 'pending' && state !== 'idle' ? 'active' : ''}`}>
                  <div className="process-tracker__connector-line" />
                  <svg width="8" height="8" viewBox="0 0 8 8" className="process-tracker__connector-arrow">
                    <path d="M2 1L6 4L2 7" fill="none" stroke="currentColor" strokeWidth="1" />
                  </svg>
                </div>
              )}
              <div className={`process-tracker__node ${state}`}>
                <span className="process-tracker__node-icon">{node.icon}</span>
                <span className="process-tracker__node-label">{node.label}</span>
                {state === 'active' && <span className="process-tracker__pulse" />}
              </div>
            </div>
          );
        })}
      </div>
      {status === 'thinking' && (
        <div className="process-tracker__status">
          <span className="process-tracker__status-dot" />
          Processing research query...
        </div>
      )}
      {status === 'complete' && (
        <div className="process-tracker__status complete">
          <span className="process-tracker__status-check">✓</span>
          Research complete — Auditor approved
        </div>
      )}
    </div>
  );
}
