import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import * as OpenApi from '../../openapi';
import { updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPutMutation } from '../../openapi/@tanstack/react-query.gen';
import { isBracket, isEmptySlot, stageItemName } from '../matches';
import { useOrganizerTranslation } from '../organizer-locales';
import { Disclosure } from '../ui';

type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;
type SlotOption = OpenApi.StageItemInputOptionFinal | OpenApi.StageItemInputOptionTentative;
type SlotBody =
  | OpenApi.StageItemInputUpdateBodyEmpty
  | OpenApi.StageItemInputUpdateBodyFinal
  | OpenApi.StageItemInputUpdateBodyTentative;

const EMPTY_SLOT = 'empty';

function slotValue(input: {
  team_id?: number | null;
  winner_from_stage_item_id?: number | null;
  winner_position?: number | null;
}) {
  if (input.team_id != null) return `team:${input.team_id}`;
  if (input.winner_from_stage_item_id != null && input.winner_position != null) {
    return `winner:${input.winner_from_stage_item_id}:${input.winner_position}`;
  }
  return EMPTY_SLOT;
}

function optionValue(option: SlotOption) {
  return 'team_id' in option
    ? `team:${option.team_id}`
    : `winner:${option.winner_from_stage_item_id}:${option.winner_position}`;
}

function slotBody(value: string): SlotBody {
  const [kind, first, second] = value.split(':');
  if (kind === 'team') return { team_id: Number(first) };
  if (kind === 'winner') {
    return { winner_from_stage_item_id: Number(first), winner_position: Number(second) };
  }
  return { team_id: null, winner_from_stage_item_id: null, winner_position: null };
}

export function StageItemSlots({
  nextStageEntries,
  options,
  stageItem,
  stageItemsById,
  teamLookup,
  tournamentId,
}: {
  nextStageEntries: OpenApi.StageItemInputUpdate[] | undefined;
  options: SlotOption[];
  stageItem: OpenApi.StageItemWithRounds;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamLookup: Map<number, OpenApi.TournamentTeamWithPlayers>;
  tournamentId: number;
}) {
  const { t } = useOrganizerTranslation();
  const filled = stageItem.inputs.filter((input) => !isEmptySlot(input)).length;
  const slot = (input: StageItemInput) => (
    <SlotSelect
      input={input}
      key={input.id}
      options={options}
      stageItemId={stageItem.id}
      stageItemsById={stageItemsById}
      teamLookup={teamLookup}
      tournamentId={tournamentId}
    />
  );
  // The first round of a bracket pairs the slots in order: slot 1 plays slot 2, slot 3 plays slot
  // 4, and so on. Seeding a bracket from groups needs to know that.
  const firstRound = isBracket(stageItem)
    ? Array.from({ length: Math.ceil(stageItem.inputs.length / 2) }, (_, index) =>
        stageItem.inputs.slice(2 * index, 2 * index + 2),
      )
    : null;

  return (
    <Disclosure
      className="collapse collapse-arrow border border-base-300 bg-base-200/60"
      open={filled < stageItem.inputs.length}
      summary={
        <>
          <span className="font-semibold">{t('slots.teams')}</span>
          <span className="block text-sm text-base-content/70">
            {t('slots.filled', { filled, total: stageItem.inputs.length })}
          </span>
        </>
      }
    >
      <div className="collapse-content grid gap-3 md:grid-cols-2">
        {firstRound
          ? firstRound.map((pair, index) => (
              <fieldset
                className="space-y-2 rounded-box border border-base-300 p-3"
                key={pair[0].id}
              >
                <legend className="px-1 text-sm font-semibold">
                  {t('slots.firstRoundMatch', { number: index + 1 })}
                </legend>
                {pair.map(slot)}
              </fieldset>
            ))
          : stageItem.inputs.map(slot)}
        {nextStageEntries ? (
          <div className="rounded-box border border-base-300 bg-base-100/50 p-4 md:col-span-2">
            <p className="text-sm text-base-content/70">{t('slots.movingIn')}</p>
            <div className="mt-3 space-y-2 text-sm">
              {nextStageEntries.map((entry) => (
                <div
                  className="flex items-start justify-between gap-3"
                  key={entry.stage_item_input.id}
                >
                  <span>
                    {entry.team.name}
                    {entry.tied_team ? (
                      <span className="block text-warning">
                        {t('slots.levelWith', {
                          team: entry.team.name,
                          tied: entry.tied_team.name,
                        })}
                      </span>
                    ) : null}
                  </span>
                  <span className="shrink-0 text-base-content/70">
                    {t('slots.slotNumber', { slot: entry.stage_item_input.slot })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </Disclosure>
  );
}

function SlotSelect({
  input,
  options,
  stageItemId,
  stageItemsById,
  teamLookup,
  tournamentId,
}: {
  input: StageItemInput;
  options: SlotOption[];
  stageItemId: number;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamLookup: Map<number, OpenApi.TournamentTeamWithPlayers>;
  tournamentId: number;
}) {
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  const currentValue = slotValue(input);
  const assign = useMutation({
    ...updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPutMutation(),
    meta: { successMessage: t('slots.updated', { slot: input.slot }) },
  });

  return (
    <div className="flex items-center justify-between gap-3 rounded-box border border-base-300 bg-base-100/50 px-3 py-2">
      <span className="text-sm font-semibold">{t('slots.slot', { slot: input.slot })}</span>
      <select
        aria-label={t('slots.slot', { slot: input.slot })}
        className="select w-auto min-w-44"
        disabled={assign.isPending}
        onChange={(event) =>
          assign.mutate({
            body: slotBody(event.target.value),
            path: {
              stage_item_id: stageItemId,
              stage_item_input_id: input.id,
              tournament_id: tournamentId,
            },
          })
        }
        // Shows the choice while it is saved, and falls back to the saved value if that fails.
        value={
          assign.isPending && assign.variables ? slotValue(assign.variables.body) : currentValue
        }
      >
        <option value={EMPTY_SLOT}>{t('slots.open')}</option>
        {options.map((option) => {
          const value = optionValue(option);
          const source =
            'team_id' in option ? undefined : stageItemsById.get(option.winner_from_stage_item_id);
          const label =
            'team_id' in option
              ? (teamLookup.get(option.team_id)?.name ??
                t('slots.unknownTeam', { id: option.team_id }))
              : shared('common.place', {
                  position: option.winner_position,
                  source: source ? stageItemName(source, shared) : '',
                });
          return (
            <option key={value} value={value}>
              {option.already_taken && value !== currentValue
                ? t('slots.taken', { option: label })
                : label}
            </option>
          );
        })}
      </select>
    </div>
  );
}
