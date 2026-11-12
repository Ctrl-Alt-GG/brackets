import { useEffect, useEffectEvent, useId, useMemo, useRef } from 'react';

import 'brackets-viewer/dist/brackets-viewer.min.js';
import 'brackets-viewer/dist/brackets-viewer.min.css';
import './bracket-viewer-canvas.css';

import { roundLabel, type BracketViewerData } from '../bracket-adapter';

const PARTICIPANT_SELECTOR = '.participant[data-participant-id]';

/**
 * `teamParticipants` maps the participants that are known teams to their team id. brackets-viewer
 * has no participant click callback, so clicks are picked up from the elements it renders.
 */
export function BracketViewerCanvas({
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

  // The data is built again whenever anything in the tournament changes. Redrawing clears the
  // bracket and loses where the visitor had scrolled to, so it only happens when this bracket's
  // own content changes.
  const serialized = useMemo(() => JSON.stringify(data), [data]);

  // Only teams get the pointer and underline, so an undecided slot never looks clickable. They
  // are links in all but markup, so they can be reached and opened from the keyboard too.
  const markTeams = useEffectEvent((container: HTMLElement) => {
    if (!onTeamClick || !teamParticipants) return;
    container.querySelectorAll<HTMLElement>(PARTICIPANT_SELECTOR).forEach((element) => {
      if (teamParticipants.has(Number(element.dataset.participantId))) {
        element.classList.add('team-link');
        element.setAttribute('role', 'link');
        element.tabIndex = 0;
      }
    });
  });

  const openTeam = (target: EventTarget) => {
    const element = (target as HTMLElement).closest<HTMLElement>(PARTICIPANT_SELECTOR);
    const teamId = element
      ? teamParticipants?.get(Number(element.dataset.participantId))
      : undefined;
    if (teamId != null) onTeamClick?.(teamId);
    return teamId != null;
  };

  useEffect(() => {
    const viewer = window.bracketsViewer;
    const container = containerRef.current;
    if (!viewer || !container) return;

    void viewer
      .render(JSON.parse(serialized) as BracketViewerData, {
        clear: true,
        customRoundName: roundLabel,
        // Only team names can be clicked, so nothing else reacts to the pointer.
        highlightParticipantOnHover: false,
        selector: `#${containerId}`,
        // The library would rank by 3 points a win, but the Standings page has the real ranking,
        // such as the rating in Swiss.
        showRankingTable: false,
      })
      .then(() => markTeams(container));

    return () => {
      container.innerHTML = '';
    };
  }, [containerId, serialized]);

  return (
    <div className="cag-bracket overflow-x-auto pb-2">
      {/* The library draws the bracket in here. The team names in it are the links; this only
          listens for them. */}
      <div
        className="brackets-viewer"
        id={containerId}
        onClick={(event) => openTeam(event.target)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && openTeam(event.target)) event.preventDefault();
        }}
        ref={containerRef}
        role="presentation"
      />
    </div>
  );
}
