import { useEffect, useId, useRef } from 'react';

import 'brackets-viewer/dist/brackets-viewer.min.js';
import 'brackets-viewer/dist/brackets-viewer.min.css';

import { roundLabel, type BracketViewerData } from '../bracket-adapter';

export function BracketViewer({ data }: { data: BracketViewerData }) {
  const containerId = `bracket-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const viewer = window.bracketsViewer;
    const container = containerRef.current;
    if (!viewer || !container) return;

    viewer.render(data, {
      clear: true,
      customRoundName: ({ roundCount, roundNumber }) => roundLabel(roundNumber, roundCount),
      selector: `#${containerId}`,
    });

    return () => {
      container.innerHTML = '';
    };
  }, [containerId, data]);

  return (
    <div className="cag-bracket overflow-x-auto pb-2">
      <div className="brackets-viewer" id={containerId} ref={containerRef} />
    </div>
  );
}
