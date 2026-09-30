import { useState, type FormEvent } from 'react';

import * as OpenApi from '../../openapi';
import { useTournamentMutation } from '../hooks';
import {
  activeTeamInputs,
  formatDateTime,
  hasTeam,
  inputLabel,
  isEmptySlot,
  isScored,
  toNumber,
} from '../utils';
import { Button, Input, Pill, Select } from '../ui';

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
  return [...stageItem.rounds].sort((left, right) => left.id - right.id);
}

function playedCount(round: Round) {
  return round.matches.filter(isScored).length;
}

function pairKey(input1Id: number | null, input2Id: number | null) {
  return `${Math.min(input1Id ?? 0, input2Id ?? 0)}-${Math.max(input1Id ?? 0, input2Id ?? 0)}`;
}

function generateRound({ tournamentId }: RoundContext, stageItemId: number) {
  return OpenApi.createRoundApiTournamentsTournamentIdRoundsPost({
    body: { name: null, stage_item_id: stageItemId },
    path: { tournament_id: tournamentId },
    throwOnError: true,
  });
}

function deleteRound({ tournamentId }: RoundContext, roundId: number) {
  return OpenApi.deleteRoundApiTournamentsTournamentIdRoundsRoundIdDelete({
    path: { round_id: roundId, tournament_id: tournamentId },
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
  const latest = published.length > 0 ? published[published.length - 1] : null;
  const isSwiss = stageItem.type === 'SWISS';

  return (
    <div className="space-y-4">
      {!isSwiss ? (
        <p className="text-sm text-zinc-400">
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
      {(isSwiss ? [...published].reverse() : published).map((round) => (
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
  const generate = useTournamentMutation(
    () => generateRound(context, stageItem.id),
    `Round ${roundNumber} pairings are ready. Publish them when they look right.`,
  );

  return (
    <div className="space-y-3 rounded-[1.25rem] border border-dashed border-white/15 bg-black/10 p-4">
      <p className="text-sm text-zinc-300">
        Every active team is paired with an opponent it hasn't played yet, as close to it in the
        standings as possible. With an odd number of teams, one team sits out. You can adjust the
        pairings before publishing them.
      </p>
      {canGenerate ? null : (
        <p className="text-sm text-zinc-400">Assign at least two teams to the slots first.</p>
      )}
      {canGenerate && previous && unplayed > 0 ? (
        <p className="text-sm text-accent-300">
          {previous.name} still has {unplayed} {unplayed === 1 ? 'match' : 'matches'} without a
          score. The pairings are based on the results entered so far.
        </p>
      ) : null}
      <Button
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
          generate.mutate();
        }}
        type="button"
      >
        {generate.isPending ? 'Generating…' : `Generate round ${roundNumber}`}
      </Button>
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
  const publish = useTournamentMutation(
    () =>
      OpenApi.updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPut({
        body: { is_draft: false, name: round.name },
        path: { round_id: round.id, tournament_id: context.tournamentId },
        throwOnError: true,
      }),
    `${round.name} is published.`,
  );
  const regenerate = useTournamentMutation(async () => {
    await deleteRound(context, round.id);
    await generateRound(context, stageItem.id);
  }, 'New pairings generated.');
  const discard = useTournamentMutation(() => deleteRound(context, round.id), 'Draft discarded.');
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
    <div className="space-y-4 rounded-[1.25rem] border border-accent-400/30 bg-accent-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-white">{round.name}</p>
          <p className="text-sm text-zinc-300">
            Only organizers can see these pairings until you publish them.
          </p>
        </div>
        <Pill tone="accent">draft</Pill>
      </div>

      {round.matches.length === 0 ? (
        <p className="text-sm text-zinc-400">No pairings yet.</p>
      ) : (
        <ul className="space-y-2">
          {round.matches.map((match) => (
            <DraftPairing context={context} disabled={busy} key={match.id} match={match} />
          ))}
        </ul>
      )}

      {unpaired.length > 0 ? (
        <p className="text-sm text-zinc-300">
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

      <div className="flex flex-wrap gap-3">
        <Button
          disabled={busy || round.matches.length === 0}
          onClick={() => publish.mutate()}
          type="button"
        >
          {publish.isPending ? 'Publishing…' : `Publish ${round.name}`}
        </Button>
        <Button
          disabled={busy}
          onClick={() => {
            if (!window.confirm('Replace these pairings with newly generated ones?')) return;
            regenerate.mutate();
          }}
          tone="secondary"
          type="button"
        >
          {regenerate.isPending ? 'Generating…' : 'Regenerate pairings'}
        </Button>
        <Button
          disabled={busy}
          onClick={() => {
            if (!window.confirm(`Discard the draft ${round.name}?`)) return;
            discard.mutate();
          }}
          tone="ghost"
          type="button"
        >
          {discard.isPending ? 'Discarding…' : 'Discard draft'}
        </Button>
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
        <span className="ml-1 text-xs text-zinc-400">
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
  const remove = useTournamentMutation(
    () =>
      OpenApi.deleteMatchApiTournamentsTournamentIdMatchesMatchIdDelete({
        path: { match_id: match.id, tournament_id: context.tournamentId },
        throwOnError: true,
      }),
    'Pairing removed.',
  );

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-black/20 px-3 py-2">
      <span className="text-sm text-white">
        <TeamWithRecord context={context} input={match.stage_item_input1} />{' '}
        <span className="text-zinc-500">vs</span>{' '}
        <TeamWithRecord context={context} input={match.stage_item_input2} />
      </span>
      <Button
        className="px-3 py-1.5"
        disabled={disabled || remove.isPending}
        onClick={() => remove.mutate()}
        tone="ghost"
        type="button"
      >
        {remove.isPending ? 'Removing…' : 'Remove'}
      </Button>
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
  const [firstId, setFirstId] = useState('');
  const [secondId, setSecondId] = useState('');
  const add = useTournamentMutation(
    () =>
      OpenApi.createMatchApiTournamentsTournamentIdMatchesPost({
        body: {
          round_id: roundId,
          stage_item_input1_id: Number(firstId),
          stage_item_input1_winner_from_match_id: null,
          stage_item_input2_id: Number(secondId),
          stage_item_input2_winner_from_match_id: null,
        },
        path: { tournament_id: context.tournamentId },
        throwOnError: true,
      }),
    'Pairing added.',
  );

  return (
    <form
      className="flex flex-wrap items-center gap-3"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        add.mutate(undefined, {
          onSuccess: () => {
            setFirstId('');
            setSecondId('');
          },
        });
      }}
    >
      <Select
        aria-label="First team"
        className="w-auto min-w-44"
        onChange={(event) => {
          setFirstId(event.target.value);
          if (event.target.value === secondId) setSecondId('');
        }}
        value={firstId}
      >
        <option value="">Pick a team</option>
        {teams.map((input) => (
          <option key={input.id} value={input.id}>
            {input.team.name}
          </option>
        ))}
      </Select>
      <span className="text-sm text-zinc-500">vs</span>
      <Select
        aria-label="Second team"
        className="w-auto min-w-44"
        onChange={(event) => setSecondId(event.target.value)}
        value={secondId}
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
      </Select>
      <Button
        disabled={disabled || add.isPending || !firstId || !secondId}
        tone="secondary"
        type="submit"
      >
        {add.isPending ? 'Adding…' : 'Add pairing'}
      </Button>
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
  const remove = useTournamentMutation(
    () => deleteRound(context, round.id),
    `${round.name} deleted.`,
  );

  return (
    <details className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4" open={open}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-white">{round.name}</p>
          <p className="text-sm text-zinc-400">
            {formatDateTime(startTime)} · {played} of {round.matches.length} matches played
          </p>
        </div>
        {round.matches.length > 0 && played === round.matches.length ? (
          <Pill tone="success">done</Pill>
        ) : null}
      </summary>
      <div className="mt-4 space-y-2">
        {round.matches.map((match) => (
          <ScoreForm context={context} key={match.id} match={match} />
        ))}
      </div>
      {canDelete ? (
        <div className="mt-4">
          <Button
            disabled={remove.isPending}
            onClick={() => {
              if (!window.confirm(`Delete ${round.name} and its results?`)) return;
              remove.mutate();
            }}
            tone="ghost"
            type="button"
          >
            {remove.isPending ? 'Deleting…' : `Delete ${round.name}`}
          </Button>
        </div>
      ) : null}
    </details>
  );
}

function ScoreForm({ context, match }: { context: RoundContext; match: Match }) {
  const ready = hasTeam(match.stage_item_input1) && hasTeam(match.stage_item_input2);
  const label1 = inputLabel(match.stage_item_input1, context.stageItemsById);
  const label2 = inputLabel(match.stage_item_input2, context.stageItemsById);
  const save = useTournamentMutation(
    (scores: { score1: number; score2: number }) =>
      OpenApi.updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPut({
        body: {
          custom_duration_minutes: match.custom_duration_minutes,
          custom_margin_minutes: match.custom_margin_minutes,
          round_id: match.round_id,
          stage_item_input1_score: scores.score1,
          stage_item_input2_score: scores.score2,
        },
        path: { match_id: match.id, tournament_id: context.tournamentId },
        throwOnError: true,
      }),
    `Score saved: ${label1} vs ${label2}.`,
  );

  return (
    <form
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 rounded-xl bg-white/5 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        save.mutate({
          score1: toNumber(formData.get('score1')),
          score2: toNumber(formData.get('score2')),
        });
      }}
      title={ready ? undefined : 'Waiting for both teams to be known'}
    >
      <span className="truncate text-sm text-white">{label1}</span>
      <Input
        aria-label={`${label1} score`}
        className="w-16 px-2 py-1.5 text-center"
        defaultValue={match.stage_item_input1_score}
        disabled={!ready}
        min={0}
        name="score1"
        required
        type="number"
      />
      <span className="truncate text-sm text-white">{label2}</span>
      <Input
        aria-label={`${label2} score`}
        className="w-16 px-2 py-1.5 text-center"
        defaultValue={match.stage_item_input2_score}
        disabled={!ready}
        min={0}
        name="score2"
        required
        type="number"
      />
      {/* Below the scores on narrow screens, next to them otherwise. */}
      <Button
        className="col-span-2 px-4 py-2 sm:col-span-1 sm:col-start-3 sm:row-span-2 sm:row-start-1"
        disabled={!ready || save.isPending}
        tone="secondary"
        type="submit"
      >
        {save.isPending ? 'Saving…' : 'Save'}
      </Button>
    </form>
  );
}
