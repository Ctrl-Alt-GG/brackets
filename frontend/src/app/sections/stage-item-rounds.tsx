import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useForm, useWatch } from 'react-hook-form';

import * as OpenApi from '../../openapi';
import {
  createMatchApiTournamentsTournamentIdMatchesPostMutation,
  createRoundApiTournamentsTournamentIdRoundsPostMutation,
  deleteMatchApiTournamentsTournamentIdMatchesMatchIdDeleteMutation,
  deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation,
  updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPutMutation,
  updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zMatchBody } from '../../openapi/zod.gen';
import {
  activeTeamInputs,
  formatDateTime,
  hasTeam,
  inputLabel,
  isEmptySlot,
  isScored,
} from '../utils';

type Match = OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;
type Round = OpenApi.RoundWithMatches;
type StageItem = OpenApi.StageItemWithRounds;
type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;

type RoundContext = {
  stageItemsById: Map<number, StageItem>;
  tournamentId: number;
};

function sortedRounds(stageItem: StageItem) {
  return stageItem.rounds.toSorted((left, right) => left.id - right.id);
}

function playedCount(round: Round) {
  return round.matches.filter(isScored).length;
}

function pairKey(input1Id: number | null, input2Id: number | null) {
  return `${Math.min(input1Id ?? 0, input2Id ?? 0)}-${Math.max(input1Id ?? 0, input2Id ?? 0)}`;
}

/** Swiss rounds are paired by the backend when they are created. */
function generateRound({ tournamentId }: RoundContext, stageItemId: number) {
  return OpenApi.createRoundApiTournamentsTournamentIdRoundsPost({
    body: { name: null, stage_item_id: stageItemId },
    path: { tournament_id: tournamentId },
    throwOnError: true,
  });
}

/** Where a stage item stands and what the organizer should do next, in one line. */
export function stageItemStatus(stageItem: StageItem) {
  const emptySlots = stageItem.inputs.filter(isEmptySlot).length;
  if (emptySlots > 0) {
    return `${stageItem.inputs.length - emptySlots} of ${stageItem.inputs.length} slots filled`;
  }

  const rounds = sortedRounds(stageItem);
  const draft = rounds.find((round) => round.is_draft);
  if (draft) return `${draft.name} is waiting to be published`;

  const current = rounds.find((round) => playedCount(round) < round.matches.length);
  if (current) {
    return `${current.name}: ${playedCount(current)} of ${current.matches.length} matches played`;
  }

  if (stageItem.type === 'SWISS') return `Ready for round ${rounds.length + 1}`;
  return 'All matches played';
}

export function StageItemRounds({
  stageItem,
  ...context
}: RoundContext & { stageItem: StageItem }) {
  const rounds = sortedRounds(stageItem);
  const draft = rounds.find((round) => round.is_draft) ?? null;
  const published = rounds.filter((round) => !round.is_draft);
  const current = published.find((round) => playedCount(round) < round.matches.length);
  const latest = published.at(-1) ?? null;
  const isSwiss = stageItem.type === 'SWISS';

  return (
    <div className="space-y-4">
      {!isSwiss ? (
        <p className="text-sm text-base-content/70">
          All rounds of a {stageItem.type_name.toLowerCase()} are created together with it. Enter
          the scores as matches finish.
          {stageItem.inputs.some(isEmptySlot)
            ? ' Assign teams to the slots to fill in the matches.'
            : ''}
        </p>
      ) : draft ? (
        <DraftRound context={context} round={draft} stageItem={stageItem} />
      ) : (
        <NextSwissRound
          context={context}
          previous={latest}
          roundNumber={rounds.length + 1}
          stageItem={stageItem}
        />
      )}
      {/* In Swiss the newest round is where the action is, so it comes first. */}
      {(isSwiss ? published.toReversed() : published).map((round) => (
        <PublishedRound
          canDelete={isSwiss && draft == null && round.id === latest?.id}
          context={context}
          key={round.id}
          open={round.id === current?.id}
          round={round}
        />
      ))}
    </div>
  );
}

function NextSwissRound({
  context,
  previous,
  roundNumber,
  stageItem,
}: {
  context: RoundContext;
  previous: Round | null;
  roundNumber: number;
  stageItem: StageItem;
}) {
  const canGenerate = activeTeamInputs(stageItem).length >= 2;
  const unplayed = previous ? previous.matches.length - playedCount(previous) : 0;
  const generate = useMutation({
    ...createRoundApiTournamentsTournamentIdRoundsPostMutation(),
    meta: {
      successMessage: `Round ${roundNumber} pairings are ready. Publish them when they look right.`,
    },
  });

  return (
    <div className="space-y-3 rounded-box border border-dashed border-base-300 bg-base-100/30 p-4">
      <p className="text-sm text-base-content/80">
        Every active team is paired with an opponent it hasn't played yet, as close to it in the
        standings as possible. With an odd number of teams, one team sits out. You can adjust the
        pairings before publishing them.
      </p>
      {canGenerate ? null : (
        <p className="text-sm text-base-content/70">
          Assign at least two teams to the slots first.
        </p>
      )}
      {canGenerate && previous && unplayed > 0 ? (
        <p className="text-sm text-warning">
          {previous.name} still has {unplayed} {unplayed === 1 ? 'match' : 'matches'} without a
          score. The pairings are based on the results entered so far.
        </p>
      ) : null}
      <button
        className="btn btn-primary"
        disabled={!canGenerate || generate.isPending}
        onClick={() => {
          if (
            previous &&
            unplayed > 0 &&
            !window.confirm(
              `${previous.name} isn't finished. Generate round ${roundNumber} anyway?`,
            )
          )
            return;
          generate.mutate({
            body: { name: null, stage_item_id: stageItem.id },
            path: { tournament_id: context.tournamentId },
          });
        }}
        type="button"
      >
        {generate.isPending ? 'Generating…' : `Generate round ${roundNumber}`}
      </button>
    </div>
  );
}

function DraftRound({
  context,
  round,
  stageItem,
}: {
  context: RoundContext;
  round: Round;
  stageItem: StageItem;
}) {
  const path = { round_id: round.id, tournament_id: context.tournamentId };
  const publish = useMutation({
    ...updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPutMutation(),
    meta: { successMessage: `${round.name} is published.` },
  });
  // Pairings come from creating a round, so new ones replace the draft with a new round.
  const regenerate = useMutation({
    meta: { successMessage: 'New pairings generated.' },
    mutationFn: async () => {
      await OpenApi.deleteRoundApiTournamentsTournamentIdRoundsRoundIdDelete({
        path,
        throwOnError: true,
      });
      await generateRound(context, stageItem.id);
    },
  });
  const discard = useMutation({
    ...deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation(),
    meta: { successMessage: 'Draft discarded.' },
  });
  const busy = publish.isPending || regenerate.isPending || discard.isPending;

  const pairedIds = new Set(
    round.matches.flatMap((match) => [match.stage_item_input1_id, match.stage_item_input2_id]),
  );
  const unpaired = activeTeamInputs(stageItem).filter((input) => !pairedIds.has(input.id));
  const playedPairs = new Set(
    stageItem.rounds
      .filter((other) => !other.is_draft)
      .flatMap((other) =>
        other.matches.map((match) =>
          pairKey(match.stage_item_input1_id, match.stage_item_input2_id),
        ),
      ),
  );

  return (
    <div className="space-y-4 rounded-box border border-accent/40 bg-accent/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{round.name}</p>
          <p className="text-sm text-base-content/80">
            Only organizers can see these pairings until you publish them.
          </p>
        </div>
        <span className="badge badge-soft badge-accent">Draft</span>
      </div>

      {round.matches.length === 0 ? (
        <p className="text-sm text-base-content/70">No pairings yet.</p>
      ) : (
        <ul className="space-y-2">
          {round.matches.map((match) => (
            <DraftPairing context={context} disabled={busy} key={match.id} match={match} />
          ))}
        </ul>
      )}

      {unpaired.length > 0 ? (
        <p className="text-sm text-base-content/80">
          Sitting out this round: {unpaired.map((input) => input.team.name).join(', ')}
        </p>
      ) : null}
      {unpaired.length >= 2 ? (
        <AddPairingForm
          context={context}
          disabled={busy}
          playedPairs={playedPairs}
          roundId={round.id}
          teams={unpaired}
        />
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          className="btn btn-primary"
          disabled={busy || round.matches.length === 0}
          onClick={() => publish.mutate({ body: { is_draft: false, name: round.name }, path })}
          type="button"
        >
          {publish.isPending ? 'Publishing…' : `Publish ${round.name}`}
        </button>
        <button
          className="btn btn-soft"
          disabled={busy}
          onClick={() => {
            if (window.confirm('Replace these pairings with newly generated ones?')) {
              regenerate.mutate();
            }
          }}
          type="button"
        >
          {regenerate.isPending ? 'Generating…' : 'Regenerate pairings'}
        </button>
        <button
          className="btn btn-ghost"
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Discard the draft ${round.name}?`)) discard.mutate({ path });
          }}
          type="button"
        >
          {discard.isPending ? 'Discarding…' : 'Discard draft'}
        </button>
      </div>
    </div>
  );
}

function TeamWithRecord({
  context,
  input,
}: {
  context: RoundContext;
  input: StageItemInput | null;
}) {
  const played = input ? input.wins + input.draws + input.losses : 0;

  return (
    <span>
      {inputLabel(input, context.stageItemsById)}
      {input && played > 0 ? (
        <span className="ml-1 text-xs text-base-content/70">
          ({input.wins}W {input.draws}D {input.losses}L)
        </span>
      ) : null}
    </span>
  );
}

function DraftPairing({
  context,
  disabled,
  match,
}: {
  context: RoundContext;
  disabled: boolean;
  match: Match;
}) {
  const remove = useMutation({
    ...deleteMatchApiTournamentsTournamentIdMatchesMatchIdDeleteMutation(),
    meta: { successMessage: 'Pairing removed.' },
  });

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-field bg-base-100/50 px-3 py-2">
      <span className="text-sm">
        <TeamWithRecord context={context} input={match.stage_item_input1} />{' '}
        <span className="text-base-content/70">vs</span>{' '}
        <TeamWithRecord context={context} input={match.stage_item_input2} />
      </span>
      <button
        className="btn btn-ghost btn-sm"
        disabled={disabled || remove.isPending}
        onClick={() =>
          remove.mutate({ path: { match_id: match.id, tournament_id: context.tournamentId } })
        }
        type="button"
      >
        {remove.isPending ? 'Removing…' : 'Remove'}
      </button>
    </li>
  );
}

function AddPairingForm({
  context,
  disabled,
  playedPairs,
  roundId,
  teams,
}: {
  context: RoundContext;
  disabled: boolean;
  playedPairs: Set<string>;
  roundId: number;
  teams: OpenApi.StageItemInputFinal[];
}) {
  const form = useForm({ defaultValues: { first: '', second: '' } });
  const [firstId, secondId] = useWatch({ control: form.control, name: ['first', 'second'] });
  const add = useMutation({
    ...createMatchApiTournamentsTournamentIdMatchesPostMutation(),
    meta: { successMessage: 'Pairing added.' },
  });

  return (
    <form
      className="flex flex-wrap items-center gap-3"
      onSubmit={form.handleSubmit(({ first, second }) =>
        add.mutate(
          {
            body: {
              round_id: roundId,
              stage_item_input1_id: Number(first),
              stage_item_input1_winner_from_match_id: null,
              stage_item_input2_id: Number(second),
              stage_item_input2_winner_from_match_id: null,
            },
            path: { tournament_id: context.tournamentId },
          },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <select
        aria-label="First team"
        className="select w-auto min-w-44"
        {...form.register('first', {
          onChange: (event) => {
            if (event.target.value === form.getValues('second')) form.setValue('second', '');
          },
        })}
      >
        <option value="">Pick a team</option>
        {teams.map((input) => (
          <option key={input.id} value={input.id}>
            {input.team.name}
          </option>
        ))}
      </select>
      <span className="text-sm text-base-content/70">vs</span>
      <select
        aria-label="Second team"
        className="select w-auto min-w-44"
        {...form.register('second')}
      >
        <option value="">Pick a team</option>
        {teams
          .filter((input) => String(input.id) !== firstId)
          .map((input) => (
            <option key={input.id} value={input.id}>
              {input.team.name}
              {firstId && playedPairs.has(pairKey(Number(firstId), input.id)) ? ' (rematch)' : ''}
            </option>
          ))}
      </select>
      <button
        className="btn btn-soft"
        disabled={disabled || add.isPending || !firstId || !secondId}
        type="submit"
      >
        {add.isPending ? 'Adding…' : 'Add pairing'}
      </button>
    </form>
  );
}

function PublishedRound({
  canDelete,
  context,
  open,
  round,
}: {
  canDelete: boolean;
  context: RoundContext;
  open: boolean;
  round: Round;
}) {
  const played = playedCount(round);
  const startTime = round.matches.find((match) => match.start_time)?.start_time ?? null;
  const remove = useMutation({
    ...deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation(),
    meta: { successMessage: `${round.name} deleted.` },
  });

  return (
    <details className="collapse collapse-arrow border border-base-300 bg-base-100/50" open={open}>
      <summary className="collapse-title">
        <span className="flex flex-wrap items-center gap-2 font-semibold">
          {round.name}
          {round.matches.length > 0 && played === round.matches.length ? (
            <span className="badge badge-soft badge-success badge-sm">Done</span>
          ) : null}
        </span>
        <span className="block text-sm text-base-content/70">
          {formatDateTime(startTime)} · {played} of {round.matches.length} matches played
        </span>
      </summary>
      <div className="collapse-content space-y-2">
        {round.matches.map((match) => (
          <ScoreForm context={context} key={match.id} match={match} />
        ))}
        {canDelete ? (
          <button
            className="btn btn-ghost mt-2"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${round.name} and its results?`)) {
                remove.mutate({
                  path: { round_id: round.id, tournament_id: context.tournamentId },
                });
              }
            }}
            type="button"
          >
            {remove.isPending ? 'Deleting…' : `Delete ${round.name}`}
          </button>
        ) : null}
      </div>
    </details>
  );
}

const scoresSchema = zMatchBody.pick({
  stage_item_input1_score: true,
  stage_item_input2_score: true,
});

function ScoreForm({ context, match }: { context: RoundContext; match: Match }) {
  const ready = hasTeam(match.stage_item_input1) && hasTeam(match.stage_item_input2);
  const label1 = inputLabel(match.stage_item_input1, context.stageItemsById);
  const label2 = inputLabel(match.stage_item_input2, context.stageItemsById);
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(scoresSchema),
    values: {
      stage_item_input1_score: match.stage_item_input1_score,
      stage_item_input2_score: match.stage_item_input2_score,
    },
  });
  const save = useMutation({
    ...updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPutMutation(),
    meta: { successMessage: `Score saved: ${label1} vs ${label2}.` },
  });

  return (
    <form
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 rounded-field bg-base-200/60 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]"
      onSubmit={form.handleSubmit((scores) =>
        save.mutate({
          body: {
            custom_duration_minutes: match.custom_duration_minutes,
            custom_margin_minutes: match.custom_margin_minutes,
            round_id: match.round_id,
            ...scores,
          },
          path: { match_id: match.id, tournament_id: context.tournamentId },
        }),
      )}
      title={ready ? undefined : 'Waiting for both teams to be known'}
    >
      <span className="truncate text-sm">{label1}</span>
      <input
        aria-label={`${label1} score`}
        className="input input-sm w-16 text-center"
        disabled={!ready}
        min={0}
        required
        type="number"
        {...form.register('stage_item_input1_score', { valueAsNumber: true })}
      />
      <span className="truncate text-sm">{label2}</span>
      <input
        aria-label={`${label2} score`}
        className="input input-sm w-16 text-center"
        disabled={!ready}
        min={0}
        required
        type="number"
        {...form.register('stage_item_input2_score', { valueAsNumber: true })}
      />
      {/* Below the scores on narrow screens, next to them otherwise. */}
      <button
        className="btn btn-soft btn-sm col-span-2 sm:col-span-1 sm:col-start-3 sm:row-span-2 sm:row-start-1"
        disabled={!ready || save.isPending}
        type="submit"
      >
        {save.isPending ? 'Saving…' : 'Save'}
      </button>
    </form>
  );
}
