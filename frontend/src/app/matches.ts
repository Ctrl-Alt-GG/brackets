/* Stage items, their slots and their matches, as the API describes them. */

import type { TFunction } from 'i18next';

import * as OpenApi from '../openapi';
import type { FlattenedMatch } from './types';

type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;

export function hasTeam(input: StageItemInput | null): input is OpenApi.StageItemInputFinal {
  return input != null && 'team' in input && input.team != null;
}

/** The team behind an input, once it is known. */
export function inputTeamId(input: StageItemInput | null) {
  return hasTeam(input) ? input.team_id : null;
}

export function involvesTeam(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
  teamId: number,
) {
  return (
    inputTeamId(match.stage_item_input1) === teamId ||
    inputTeamId(match.stage_item_input2) === teamId
  );
}

export function isBracket(stageItem: OpenApi.StageItemWithRounds) {
  return stageItem.type === 'SINGLE_ELIMINATION';
}

/** "Round robin", "Swiss" and so on, in the language of the page. */
export function stageTypeName(stageItem: Pick<OpenApi.StageItemWithRounds, 'type'>, t: TFunction) {
  return t(`stageType.${stageItem.type}`);
}

/**
 * The name the site stores for a stage item created without one, in English. It is shown as the
 * format's name, in the language of the page.
 */
const DEFAULT_STAGE_ITEM_NAMES: Record<OpenApi.StageType, string> = {
  ROUND_ROBIN: 'Round Robin',
  SINGLE_ELIMINATION: 'Single Elimination',
  SWISS: 'Swiss',
};

/** The name the organizers gave the stage item, or else its format. */
export function stageItemName(
  stageItem: Pick<OpenApi.StageItemWithRounds, 'name' | 'type'>,
  t: TFunction,
) {
  return stageItem.name && stageItem.name !== DEFAULT_STAGE_ITEM_NAMES[stageItem.type]
    ? stageItem.name
    : stageTypeName(stageItem, t);
}

/**
 * A round's name. The site names the rounds it creates "Round 01" and so on, in English; those
 * are shown in the language of the page, and names the organizers gave stay as they are.
 */
export function roundName(round: Pick<OpenApi.RoundWithMatches, 'name'>, t: TFunction) {
  const number = /^Round (\d+)$/.exec(round.name)?.[1];
  return number ? t('round.generated', { number: Number(number), padded: number }) : round.name;
}

/** A stage's name. A new stage is called "Stage", which is shown in the language of the page. */
export function stageName(stage: Pick<OpenApi.StageWithStageItems, 'name'>, t: TFunction) {
  return stage.name === 'Stage' ? t('round.defaultStage') : stage.name;
}

/** Whether the Bracket page draws the stage item: its knockout bracket, or its Swiss rounds. */
export function hasBracketView(stageItem: OpenApi.StageItemWithRounds) {
  return isBracket(stageItem) || stageItem.type === 'SWISS';
}

export function isEmptySlot(input: StageItemInput) {
  return input.team_id == null && input.winner_from_stage_item_id == null;
}

export function activeTeamInputs(stageItem: OpenApi.StageItemWithRounds) {
  return stageItem.inputs.filter(
    (input): input is OpenApi.StageItemInputFinal => hasTeam(input) && input.team.active,
  );
}

/**
 * The teams of a stage item with their results, best first. The backend ranks them, in the same
 * order in which teams advance to the next stage.
 */
export function stageItemStandings(
  stageItem: OpenApi.StageItemWithRounds,
  standings: Record<string, OpenApi.StageItemInputStanding[]>,
) {
  const inputs = new Map(stageItem.inputs.filter(hasTeam).map((input) => [input.id, input]));
  return (standings[String(stageItem.id)] ?? []).flatMap((standing) => {
    const input = inputs.get(standing.stage_item_input_id);
    return input ? [{ input, standing }] : [];
  });
}

/** Who plays in a slot: the team, the place of an earlier stage item it takes, or undecided. */
export function inputLabel(
  input: StageItemInput | null,
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>,
  t: TFunction,
) {
  if (hasTeam(input)) return input.team.name;
  const source =
    input?.winner_from_stage_item_id != null
      ? stageItemsById.get(input.winner_from_stage_item_id)
      : undefined;
  return source && input?.winner_position != null
    ? t('common.place', { position: input.winner_position, source: stageItemName(source, t) })
    : t('common.undecided');
}

/** Whether the match has a result. An unplayed match reads 0-0, so the API says which it is. */
export function isScored(match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive) {
  return match.played;
}

export type MatchOutcome = 1 | 2 | 'draw' | null;

export function matchWinner(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
): MatchOutcome {
  if (!isScored(match)) return null;
  if (match.stage_item_input1_score > match.stage_item_input2_score) return 1;
  if (match.stage_item_input2_score > match.stage_item_input1_score) return 2;
  return 'draw';
}

export function compareMatchesByTime(left: FlattenedMatch, right: FlattenedMatch) {
  const leftTime = left.match.start_time
    ? new Date(left.match.start_time).getTime()
    : Number.MAX_SAFE_INTEGER;
  const rightTime = right.match.start_time
    ? new Date(right.match.start_time).getTime()
    : Number.MAX_SAFE_INTEGER;
  if (leftTime !== rightTime) return leftTime - rightTime;
  if (left.round.id !== right.round.id) return left.round.id - right.round.id;
  return left.match.id - right.match.id;
}

export function flattenMatches(stages: OpenApi.StageWithStageItems[]) {
  return stages.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) =>
      stageItem.rounds.flatMap((round) =>
        round.matches.map((match) => ({
          match,
          round,
          stage,
          stageItem,
        })),
      ),
    ),
  );
}
