import * as OpenApi from '../../openapi';
import type { FlattenedMatch } from '../types';
import {
  cx,
  formatDateTime,
  inputLabel,
  MATCH_STATUS_LABELS,
  matchStatus,
  matchWinner,
} from '../utils';

function Side({
  label,
  score,
  showScore,
  isWinner,
  isLoser,
  size,
}: {
  isLoser: boolean;
  isWinner: boolean;
  label: string;
  score: number;
  showScore: boolean;
  size: 'lg' | 'md';
}) {
  return (
    <div
      className={cx(
        'flex items-center justify-between gap-3 rounded-xl px-3 py-2',
        isWinner ? 'bg-emerald-500/10' : null,
      )}
    >
      <span
        className={cx(
          'truncate',
          size === 'lg' ? 'text-xl' : 'text-sm',
          isWinner ? 'font-semibold text-white' : null,
          isLoser ? 'text-zinc-500' : 'text-zinc-200',
        )}
      >
        {label}
      </span>
      <span
        className={cx(
          'shrink-0 font-semibold tabular-nums',
          size === 'lg' ? 'text-2xl' : 'text-base',
          showScore ? (isWinner ? 'text-emerald-300' : 'text-zinc-400') : 'text-zinc-600',
        )}
      >
        {showScore ? score : '–'}
      </span>
    </div>
  );
}

export function MatchCard({
  entry,
  showContext = true,
  size = 'md',
  stageItemsById,
}: {
  entry: FlattenedMatch;
  showContext?: boolean;
  size?: 'lg' | 'md';
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
}) {
  const { match, round, stage, stageItem } = entry;
  const status = matchStatus(match);
  const winner = matchWinner(match);
  const showScore = status === 'finished' || status === 'live';

  return (
    <div className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {showContext ? (
          <p className="text-xs text-zinc-500">
            {stageItem.name || stageItem.type_name} · {round.name}
          </p>
        ) : (
          <p className="text-xs text-zinc-500">{stage.name}</p>
        )}
        <span
          className={cx(
            'rounded-full px-2.5 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.15em]',
            status === 'live' ? 'bg-brand-500/20 text-brand-200' : null,
            status === 'finished' ? 'bg-emerald-500/15 text-emerald-200' : null,
            status === 'scheduled' ? 'bg-white/10 text-zinc-300' : null,
            status === 'waiting' ? 'bg-white/5 text-zinc-500' : null,
          )}
        >
          {MATCH_STATUS_LABELS[status]}
        </span>
      </div>

      <div className="mt-3 space-y-1">
        <Side
          isLoser={winner === 2}
          isWinner={winner === 1}
          label={inputLabel(match.stage_item_input1, stageItemsById)}
          score={match.stage_item_input1_score}
          showScore={showScore}
          size={size}
        />
        <Side
          isLoser={winner === 1}
          isWinner={winner === 2}
          label={inputLabel(match.stage_item_input2, stageItemsById)}
          score={match.stage_item_input2_score}
          showScore={showScore}
          size={size}
        />
      </div>

      <p className="mt-3 text-xs text-zinc-500">
        {formatDateTime(match.start_time)}
        {match.court ? ` · ${match.court.name}` : ''}
      </p>
    </div>
  );
}
