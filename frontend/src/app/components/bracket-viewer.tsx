import { useEffect, useEffectEvent, useId, useRef } from 'react';

import 'brackets-viewer/dist/brackets-viewer.min.js';
import 'brackets-viewer/dist/brackets-viewer.min.css';

import { roundLabel, type BracketViewerData } from '../bracket-adapter';

const PARTICIPANT_SELECTOR = '.participant[data-participant-id]';

/**
 * `teamParticipants` maps the participants that are known teams to their team id. brackets-viewer
 * has no participant click callback, so clicks are picked up from the elements it renders.
 */
export function BracketViewer({
  data,
  onTeamClick,
  teamParticipants,
}: {
  data: BracketViewerData;
  onTeamClick?: (teamId: number) => void;
  teamParticipants?: ReadonlyMap<number, number>;
}) {
  const containerId = `bracket-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const containerRef = useRef<HTMLDivElement>(null);

  // Only teams get the pointer and underline, so an undecided slot never looks clickable.
  const markTeams = useEffectEvent((container: HTMLElement) => {
    if (!onTeamClick || !teamParticipants) return;
    container.querySelectorAll<HTMLElement>(PARTICIPANT_SELECTOR).forEach((element) => {
      if (teamParticipants.has(Number(element.dataset.participantId))) {
        element.classList.add('team-link');
      }
    });
  });

  useEffect(() => {
    const viewer = window.bracketsViewer;
    const container = containerRef.current;
    if (!viewer || !container) return;

    void viewer
      .render(data, {
        clear: true,
        customRoundName: ({ roundCount, roundNumber }) => roundLabel(roundNumber, roundCount),
        selector: `#${containerId}`,
      })
      .then(() => markTeams(container));

    return () => {
      container.innerHTML = '';
    };
  }, [containerId, data]);

  return (
    <div className="cag-bracket overflow-x-auto pb-2">
      <div
        className="brackets-viewer"
        id={containerId}
        onClick={(event) => {
          const element = (event.target as HTMLElement).closest<HTMLElement>(PARTICIPANT_SELECTOR);
          const teamId = element
            ? teamParticipants?.get(Number(element.dataset.participantId))
            : undefined;
          if (teamId != null) onTeamClick?.(teamId);
        }}
        ref={containerRef}
      />
    </div>
  );
}
