import * as OpenApi from '../../openapi';
import { useTournamentMutation } from '../hooks';
import { isEmptySlot } from '../utils';
import { Select } from '../ui';

type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;
type SlotOption = OpenApi.StageItemInputOptionFinal | OpenApi.StageItemInputOptionTentative;

const EMPTY_SLOT = 'empty';

function slotValue(input: StageItemInput) {
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

function slotBody(
  value: string,
):
  | OpenApi.StageItemInputUpdateBodyEmpty
  | OpenApi.StageItemInputUpdateBodyFinal
  | OpenApi.StageItemInputUpdateBodyTentative {
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
      className="rounded-[1.5rem] border border-white/10 bg-white/5 p-4"
      open={filled < stageItem.inputs.length}
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
        <h5 className="font-semibold text-white">Teams</h5>
        <span className="text-sm text-zinc-400">
          {filled} of {stageItem.inputs.length} slots filled
        </span>
      </summary>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
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
      </div>
      {nextStageEntries ? (
        <div className="mt-4 rounded-[1.25rem] border border-white/10 bg-black/20 p-4">
          <p className="text-sm text-zinc-400">Teams moving in when this stage starts</p>
          <div className="mt-3 space-y-2 text-sm text-zinc-200">
            {nextStageEntries.map((entry) => (
              <div className="flex items-center justify-between" key={entry.stage_item_input.id}>
                <span>{entry.team.name}</span>
                <span className="text-zinc-400">slot {entry.stage_item_input.slot}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
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
  const assign = useTournamentMutation(
    (value: string) =>
      OpenApi.updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPut(
        {
          body: slotBody(value),
          path: {
            stage_item_id: stageItemId,
            stage_item_input_id: input.id,
            tournament_id: tournamentId,
          },
          throwOnError: true,
        },
      ),
    `Slot ${input.slot} updated.`,
  );

  return (
    <div className="flex items-center justify-between gap-3 rounded-[1.25rem] border border-white/10 bg-black/20 px-3 py-2">
      <span className="text-sm font-semibold text-white">Slot {input.slot}</span>
      <Select
        aria-label={`Slot ${input.slot}`}
        className="w-auto min-w-44"
        disabled={assign.isPending}
        onChange={(event) => assign.mutate(event.target.value)}
        // Shows the choice while it is saved, and falls back to the saved value if that fails.
        value={assign.isPending ? (assign.variables ?? currentValue) : currentValue}
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
      </Select>
    </div>
  );
}
