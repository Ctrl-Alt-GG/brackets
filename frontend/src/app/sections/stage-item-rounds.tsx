import { useMutation } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import * as OpenApi from '../../openapi';
import {
  createMatchApiTournamentsTournamentIdMatchesPostMutation,
  createRoundApiTournamentsTournamentIdRoundsPostMutation,
  deleteMatchApiTournamentsTournamentIdMatchesMatchIdDeleteMutation,
  deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation,
  regenerateRoundApiTournamentsTournamentIdRoundsRoundIdRegeneratePostMutation,
  updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { ScoreForm } from '../components/score-form';
import { confirm } from '../confirm';
import { useCreateForm } from '../create-form';
import { formatDateTime } from '../format';
import {
  activeTeamInputs,
  inputLabel,
  inputTeamId,
  isBracket,
  isEmptySlot,
  isScored,
  roundName,
  stageTypeName,
} from '../matches';
import { useOrganizerTranslation } from '../organizer-locales';
import { Disclosure } from '../ui';

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

/**
 * Where a stage item stands and what the organizer should do next, in one line. `t` gives the
 * organizer texts, `shared` the round names that every page shows.
 */
export function stageItemStatus(
  stageItem: StageItem,
  t: TFunction<'organizer'>,
  shared: TFunction,
) {
  const emptySlots = stageItem.inputs.filter(isEmptySlot).length;
  if (emptySlots > 0) {
    return t('slots.filled', {
      filled: stageItem.inputs.length - emptySlots,
      total: stageItem.inputs.length,
    });
  }

  const rounds = sortedRounds(stageItem);
  const draft = rounds.find((round) => round.is_draft);
  if (draft) return t('rounds.waitingToPublish', { round: roundName(draft, shared) });

  const current = rounds.find((round) => playedCount(round) < round.matches.length);
  if (current) {
    return t('rounds.progress', {
      played: playedCount(current),
      round: roundName(current, shared),
      total: current.matches.length,
    });
  }

  if (stageItem.type === 'SWISS') return t('rounds.readyForRound', { number: rounds.length + 1 });
  return t('rounds.allPlayed');
}

export function StageItemRounds({
  stageItem,
  ...context
}: RoundContext & { stageItem: StageItem }) {
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
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
          {t('rounds.createdTogether', {
            format: stageTypeName(stageItem, shared).toLowerCase(),
          })}
          {stageItem.inputs.some(isEmptySlot) ? ` ${t('rounds.assignTeams')}` : ''}
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
          allowsDraw={!isBracket(stageItem)}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const canGenerate = activeTeamInputs(stageItem).length >= 2;
  const unplayed = previous ? previous.matches.length - playedCount(previous) : 0;
  const previousName = previous ? roundName(previous, shared) : '';
  const generate = useMutation({
    ...createRoundApiTournamentsTournamentIdRoundsPostMutation(),
    meta: { successMessage: t('rounds.pairingsReady', { number: roundNumber }) },
  });

  return (
    <div className="space-y-3 rounded-box border border-dashed border-base-300 bg-base-100/30 p-4">
      <p className="text-sm text-base-content/80">{t('rounds.swissHelp')}</p>
      {canGenerate ? null : (
        <p className="text-sm text-base-content/70">{t('rounds.needTwoTeams')}</p>
      )}
      {canGenerate && previous && unplayed > 0 ? (
        <p className="text-sm text-warning">
          {t('rounds.unplayed', { count: unplayed, round: previousName })}
        </p>
      ) : null}
      <button
        className="btn btn-primary"
        disabled={!canGenerate || generate.isPending}
        onClick={async () => {
          if (
            previous &&
            unplayed > 0 &&
            !(await confirm({
              confirmLabel: t('rounds.generate', { number: roundNumber }),
              message: t('rounds.generateAnyway', { number: roundNumber, round: previousName }),
            }))
          )
            return;
          generate.mutate({
            body: { name: null, stage_item_id: stageItem.id },
            path: { tournament_id: context.tournamentId },
          });
        }}
        type="button"
      >
        {generate.isPending
          ? t('common.generating')
          : t('rounds.generate', { number: roundNumber })}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const name = roundName(round, shared);
  const path = { round_id: round.id, tournament_id: context.tournamentId };
  const publish = useMutation({
    ...updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPutMutation(),
    meta: { successMessage: t('rounds.published', { round: name }) },
  });
  // Replacement is one server transaction: if pairing fails, the original draft stays intact.
  const regenerate = useMutation({
    ...regenerateRoundApiTournamentsTournamentIdRoundsRoundIdRegeneratePostMutation(),
    meta: { successMessage: t('rounds.regenerated') },
  });
  const discard = useMutation({
    ...deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation(),
    meta: { successMessage: t('rounds.discarded') },
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
          <p className="font-semibold">{name}</p>
          <p className="text-sm text-base-content/80">{t('rounds.draftHelp')}</p>
        </div>
        <span className="badge badge-soft badge-accent">{t('rounds.draft')}</span>
      </div>

      {round.matches.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('rounds.noPairings')}</p>
      ) : (
        <ul className="space-y-2">
          {round.matches.map((match) => (
            <DraftPairing context={context} disabled={busy} key={match.id} match={match} />
          ))}
        </ul>
      )}

      {unpaired.length > 0 ? (
        <p className="text-sm text-base-content/80">
          {t('rounds.sittingOut', {
            teams: unpaired.map((input) => input.team.name).join(', '),
          })}
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
          {publish.isPending ? t('rounds.publishing') : t('rounds.publish', { round: name })}
        </button>
        <button
          className="btn btn-soft"
          disabled={busy}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: t('rounds.regenerate'),
                message: t('rounds.regenerateQuestion'),
              })
            ) {
              regenerate.mutate({ path });
            }
          }}
          type="button"
        >
          {regenerate.isPending ? t('common.generating') : t('rounds.regenerate')}
        </button>
        <button
          className="btn btn-ghost"
          disabled={busy}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: t('rounds.discard'),
                destructive: true,
                message: t('rounds.discardQuestion', { round: name }),
              })
            ) {
              discard.mutate({ path });
            }
          }}
          type="button"
        >
          {discard.isPending ? t('rounds.discarding') : t('rounds.discard')}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const played = input ? input.wins + input.draws + input.losses : 0;

  return (
    <span>
      {inputLabel(input, context.stageItemsById, shared)}
      {input && played > 0 ? (
        <span className="ml-1 text-xs text-base-content/70">
          {t('rounds.record', { draws: input.draws, losses: input.losses, wins: input.wins })}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const remove = useMutation({
    ...deleteMatchApiTournamentsTournamentIdMatchesMatchIdDeleteMutation(),
    meta: { successMessage: t('rounds.pairingRemoved') },
  });

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-field bg-base-100/50 px-3 py-2">
      <span className="text-sm">
        <TeamWithRecord context={context} input={match.stage_item_input1} />{' '}
        <span className="text-base-content/70">{shared('common.vs')}</span>{' '}
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
        {remove.isPending ? t('common.removing') : t('common.remove')}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const form = useCreateForm({ defaultValues: { first: '', second: '' } });
  const [firstId, secondId] = useWatch({ control: form.control, name: ['first', 'second'] });
  const add = useMutation({
    ...createMatchApiTournamentsTournamentIdMatchesPostMutation(),
    meta: { successMessage: t('rounds.pairingAdded') },
  });

  return (
    <form
      className="flex flex-wrap items-center gap-3"
      onSubmit={form.submitWith(({ first, second }) =>
        add.mutateAsync({
          body: {
            round_id: roundId,
            stage_item_input1_id: Number(first),
            stage_item_input1_winner_from_match_id: null,
            stage_item_input2_id: Number(second),
            stage_item_input2_winner_from_match_id: null,
          },
          path: { tournament_id: context.tournamentId },
        }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <select
          aria-label={t('rounds.firstTeam')}
          className="select w-auto min-w-44"
          {...form.register('first', {
            onChange: (event) => {
              if (event.target.value === form.getValues('second')) form.setValue('second', '');
            },
          })}
        >
          <option value="">{t('rounds.pickTeam')}</option>
          {teams.map((input) => (
            <option key={input.id} value={input.id}>
              {input.team.name}
            </option>
          ))}
        </select>
        <span className="text-sm text-base-content/70">{shared('common.vs')}</span>
        <select
          aria-label={t('rounds.secondTeam')}
          className="select w-auto min-w-44"
          {...form.register('second')}
        >
          <option value="">{t('rounds.pickTeam')}</option>
          {teams
            .filter((input) => String(input.id) !== firstId)
            .map((input) => (
              <option key={input.id} value={input.id}>
                {firstId && playedPairs.has(pairKey(Number(firstId), input.id))
                  ? t('rounds.rematch', { team: input.team.name })
                  : input.team.name}
              </option>
            ))}
        </select>
        <button className="btn btn-soft" disabled={disabled || !firstId || !secondId} type="submit">
          {add.isPending ? t('common.adding') : t('rounds.addPairing')}
        </button>
      </fieldset>
    </form>
  );
}

function PublishedRound({
  allowsDraw,
  canDelete,
  context,
  open,
  round,
}: {
  allowsDraw: boolean;
  canDelete: boolean;
  context: RoundContext;
  open: boolean;
  round: Round;
}) {
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const name = roundName(round, shared);
  const played = playedCount(round);
  const startTime = round.matches.find((match) => match.start_time)?.start_time ?? null;
  const remove = useMutation({
    ...deleteRoundApiTournamentsTournamentIdRoundsRoundIdDeleteMutation(),
    meta: { successMessage: t('rounds.deleted', { round: name }) },
  });

  return (
    <Disclosure
      className="collapse collapse-arrow border border-base-300 bg-base-100/50"
      open={open}
      summary={
        <>
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {name}
            {round.matches.length > 0 && played === round.matches.length ? (
              <span className="badge badge-soft badge-success badge-sm">{t('rounds.done')}</span>
            ) : null}
          </span>
          <span className="block text-sm text-base-content/70">
            {t('rounds.summary', {
              played,
              time: startTime ? formatDateTime(startTime) : shared('time.notScheduled'),
              total: round.matches.length,
            })}
          </span>
        </>
      }
    >
      <div className="collapse-content space-y-2">
        {round.matches.map((match) => (
          <ScoreForm
            allowsDraw={allowsDraw}
            key={`${match.id}:${inputTeamId(match.stage_item_input1)}:${inputTeamId(match.stage_item_input2)}`}
            label1={inputLabel(match.stage_item_input1, context.stageItemsById, shared)}
            label2={inputLabel(match.stage_item_input2, context.stageItemsById, shared)}
            match={match}
            tournamentId={context.tournamentId}
          />
        ))}
        {canDelete ? (
          <button
            className="btn btn-ghost mt-2"
            disabled={remove.isPending}
            onClick={async () => {
              if (
                await confirm({
                  confirmLabel: t('rounds.deleteRound', { round: name }),
                  destructive: true,
                  message: t('rounds.deleteQuestion', { round: name }),
                })
              ) {
                remove.mutate({
                  path: { round_id: round.id, tournament_id: context.tournamentId },
                });
              }
            }}
            type="button"
          >
            {remove.isPending ? t('common.deleting') : t('rounds.deleteRound', { round: name })}
          </button>
        ) : null}
      </div>
    </Disclosure>
  );
}
