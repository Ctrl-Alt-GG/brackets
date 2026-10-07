import * as OpenApi from '../../openapi';
import { useTournamentContext } from '../tournament-context';
import type { FlattenedMatch } from '../types';
import {
  cx,
  formatMatchTime,
  inputLabel,
  inputTeamId,
  MATCH_STATUS_LABELS,
  matchStatus,
  matchWinner,
  type MatchStatus,
} from '../utils';
import { TeamLink } from './team-link';

const STATUS_BADGES: Record<MatchStatus, string> = {
  finished: 'badge-success',
  live: 'badge-error',
  scheduled: '',
  waiting: 'badge-ghost',
};

function Side({
  input,
  isLoser,
  isMine,
  isWinner,
  score,
  showScore,
  size,
  stageItemsById,
}: {
  input: OpenApi.MatchWithDetails['stage_item_input1'];
  isLoser: boolean;
  isMine: boolean;
  isWinner: boolean;
  score: number;
  showScore: boolean;
  size: 'lg' | 'md';
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
}) {
  return (
    <div
      className={cx(
        'flex items-center justify-between gap-3 rounded-field px-3 py-2',
        isWinner && 'bg-success/10',
      )}
    >
      <TeamLink
        className={cx(
          'min-w-0 truncate',
          size === 'lg' ? 'text-xl' : 'text-sm',
          isWinner && 'font-semibold',
          isMine
            ? 'text-accent'
            : isWinner
              ? 'text-base-content'
              : isLoser
                ? 'text-base-content/60'
                : 'text-base-content/90',
        )}
        teamId={inputTeamId(input)}
      >
        {inputLabel(input, stageItemsById)}
      </TeamLink>
      <span
        className={cx(
          'shrink-0 font-semibold tabular-nums',
          size === 'lg' ? 'text-2xl' : 'text-base',
          showScore ? (isWinner ? 'text-success' : 'text-base-content/80') : 'text-base-content/50',
        )}
      >
        {showScore ? score : '–'}
      </span>
    </div>
  );
}

export function MatchCard({
  entry,
  showTime = true,
  size = 'md',
  stageItemsById,
}: {
  entry: FlattenedMatch;
  showTime?: boolean;
  size?: 'lg' | 'md';
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
}) {
  const { myTeamId } = useTournamentContext();
  const { match, round, stageItem } = entry;
  const status = matchStatus(match);
  const winner = matchWinner(match);
  const showScore = status === 'finished' || status === 'live';
  const isMine1 = myTeamId != null && inputTeamId(match.stage_item_input1) === myTeamId;
  const isMine2 = myTeamId != null && inputTeamId(match.stage_item_input2) === myTeamId;

  return (
    <div
      className={cx(
        'card border bg-base-100/60 p-4',
        isMine1 || isMine2 ? 'border-accent/60' : 'border-base-300',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-base-content/70">
          {stageItem.name || stageItem.type_name} · {round.name}
        </p>
        <span className={cx('badge badge-soft badge-sm', STATUS_BADGES[status])}>
          {status === 'live' ? (
            <span aria-hidden="true" className="status status-error motion-safe:animate-pulse" />
          ) : null}
          {MATCH_STATUS_LABELS[status]}
        </span>
      </div>

      <div className="mt-3 space-y-1">
        <Side
          input={match.stage_item_input1}
          isLoser={winner === 2}
          isMine={isMine1}
          isWinner={winner === 1}
          score={match.stage_item_input1_score}
          showScore={showScore}
          size={size}
          stageItemsById={stageItemsById}
        />
        <Side
          input={match.stage_item_input2}
          isLoser={winner === 1}
          isMine={isMine2}
          isWinner={winner === 2}
          score={match.stage_item_input2_score}
          showScore={showScore}
          size={size}
          stageItemsById={stageItemsById}
        />
      </div>

      {showTime ? (
        <p className="mt-3 text-xs text-base-content/70">{formatMatchTime(match.start_time)}</p>
      ) : null}
    </div>
  );
}
