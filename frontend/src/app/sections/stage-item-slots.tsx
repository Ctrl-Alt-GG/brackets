import { useMutation } from '@tanstack/react-query';

import * as OpenApi from '../../openapi';
import { updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPutMutation } from '../../openapi/@tanstack/react-query.gen';
import { isEmptySlot } from '../utils';

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
  teamLookup: Map<number, OpenApi.FullTeamWithPlayers>;
  tournamentId: number;
}) {
  const filled = stageItem.inputs.filter((input) => !isEmptySlot(input)).length;

  return (
    <details
      className="collapse collapse-arrow border border-base-300 bg-base-200/60"
      open={filled < stageItem.inputs.length}
    >
      <summary className="collapse-title">
        <span className="font-semibold">Teams</span>
        <span className="block text-sm text-base-content/70">
          {filled} of {stageItem.inputs.length} slots filled
        </span>
      </summary>
      <div className="collapse-content grid gap-3 md:grid-cols-2">
        {stageItem.inputs.map((input) => (
          <SlotSelect
            input={input}
            key={input.id}
            options={options}
            stageItemId={stageItem.id}
            stageItemsById={stageItemsById}
            teamLookup={teamLookup}
            tournamentId={tournamentId}
          />
        ))}
        {nextStageEntries ? (
          <div className="rounded-box border border-base-300 bg-base-100/50 p-4 md:col-span-2">
            <p className="text-sm text-base-content/70">Teams moving in when this stage starts</p>
            <div className="mt-3 space-y-2 text-sm">
              {nextStageEntries.map((entry) => (
                <div className="flex items-center justify-between" key={entry.stage_item_input.id}>
                  <span>{entry.team.name}</span>
                  <span className="text-base-content/70">slot {entry.stage_item_input.slot}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </details>
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
  teamLookup: Map<number, OpenApi.FullTeamWithPlayers>;
  tournamentId: number;
}) {
  const currentValue = slotValue(input);
  const assign = useMutation({
    ...updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPutMutation(),
    meta: { successMessage: `Slot ${input.slot} updated.` },
  });

  return (
    <div className="flex items-center justify-between gap-3 rounded-box border border-base-300 bg-base-100/50 px-3 py-2">
      <span className="text-sm font-semibold">Slot {input.slot}</span>
      <select
        aria-label={`Slot ${input.slot}`}
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
        <option value={EMPTY_SLOT}>Open slot</option>
        {options.map((option) => {
          const value = optionValue(option);
          const taken = option.already_taken && value !== currentValue ? ' (taken)' : '';
          if ('team_id' in option) {
            return (
              <option key={value} value={value}>
                {teamLookup.get(option.team_id)?.name ?? `Team #${option.team_id}`}
                {taken}
              </option>
            );
          }
          const source = stageItemsById.get(option.winner_from_stage_item_id);
          return (
            <option key={value} value={value}>
              {source?.name || source?.type_name} #{option.winner_position}
              {taken}
            </option>
          );
        })}
      </select>
    </div>
  );
}
