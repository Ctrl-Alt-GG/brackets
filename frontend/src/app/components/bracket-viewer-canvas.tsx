import type { TFunction } from 'i18next';
import { useEffect, useEffectEvent, useId, useMemo, useRef, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';

import 'brackets-viewer/dist/brackets-viewer.min.js';
import 'brackets-viewer/dist/brackets-viewer.min.css';
import './bracket-viewer-canvas.css';

import { roundLabel, type BracketViewerData } from '../bracket-adapter';

const PARTICIPANT_SELECTOR = '.participant[data-participant-id]';

/**
 * The labels brackets-viewer writes itself: above every match, and for a slot of the first round
 * that is still open. It translates them with an i18next of its own, which follows the browser's
 * language rather than the page's, and falls back to its English. Its English, and its French,
 * the only other language it has, get the page's labels, so they show whatever it detects.
 */
function viewerLabels(t: TFunction) {
  // The viewer fills in its own placeholders, such as {{matchNumber}}.
  const raw = { skipInterpolation: true } as const;
  return {
    abbreviations: {
      forfeit: t('viewer.forfeit', raw),
      loss: t('viewer.loss', raw),
      win: t('viewer.win', raw),
    },
    common: { bye: t('viewer.bye', raw) },
    'match-label': {
      default: t('viewer.match', raw),
      'standard-bracket-final': t('viewer.final', raw),
      'standard-bracket-semi-final': t('viewer.semiFinal', raw),
    },
    'origin-hint': { seed: t('viewer.seed', raw) },
  };
}

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
  const { t } = useTranslation();
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

    const labels = viewerLabels(t);
    void Promise.all([viewer.addLocale('en', labels), viewer.addLocale('fr', labels)])
      .then(() =>
        viewer.render(JSON.parse(serialized) as BracketViewerData, {
          clear: true,
          customRoundName: (info) => roundLabel(info, t),
          // Only team names can be clicked, so nothing else reacts to the pointer.
          highlightParticipantOnHover: false,
          selector: `#${containerId}`,
          // The library would rank by 3 points a win, but the Standings page has the real
          // ranking, such as the rating in Swiss.
          showRankingTable: false,
        }),
      )
      .then(() => markTeams(container));

    return () => {
      container.innerHTML = '';
    };
    // `t` changes with the language, which the labels follow.
  }, [containerId, serialized, t]);

  return (
    <div
      className="cag-bracket overflow-x-auto pb-2"
      // A CSS string, for the label of an undecided slot.
      style={{ '--undecided-label': JSON.stringify(t('common.undecided')) } as CSSProperties}
    >
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
