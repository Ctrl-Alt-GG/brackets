import { useTranslation } from 'react-i18next';

import * as OpenApi from '../../openapi';
import { tournamentPhase, type TournamentPhase } from '../utils';

const PHASE_CLASSES: Record<TournamentPhase, string> = {
  finished: '',
  running: 'badge-error',
  upcoming: 'badge-accent',
};

export function TournamentStatusBadge({ tournament }: { tournament: OpenApi.Tournament }) {
  const { t } = useTranslation();
  const phase = tournamentPhase(tournament);
  return (
    <span className={`badge badge-soft badge-sm ${PHASE_CLASSES[phase]}`}>
      {phase === 'running' ? (
        <span aria-hidden="true" className="status status-error motion-safe:animate-pulse" />
      ) : null}
      {t(`phase.${phase}`)}
    </span>
  );
}
