import * as OpenApi from '../../openapi';
import { TOURNAMENT_PHASE_LABELS, tournamentPhase, type TournamentPhase } from '../utils';

const PHASE_CLASSES: Record<TournamentPhase, string> = {
  finished: '',
  running: 'badge-error',
  upcoming: 'badge-accent',
};

export function TournamentStatusBadge({ tournament }: { tournament: OpenApi.Tournament }) {
  const phase = tournamentPhase(tournament);
  return (
    <span className={`badge badge-soft badge-sm ${PHASE_CLASSES[phase]}`}>
      {phase === 'running' ? (
        <span aria-hidden="true" className="status status-error motion-safe:animate-pulse" />
      ) : null}
      {TOURNAMENT_PHASE_LABELS[phase]}
    </span>
  );
}
