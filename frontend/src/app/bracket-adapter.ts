import * as OpenApi from '../openapi';
import { inputLabel, isScored } from './utils';

// Subset of brackets-model that brackets-viewer's render() consumes.
type ParticipantResult = {
  id: number | null;
  position?: number;
  result?: 'draw' | 'loss' | 'win';
  score?: number;
};

type ViewerMatch = {
  child_count: number;
  group_id: number;
  id: number;
  number: number;
  opponent1: ParticipantResult | null;
  opponent2: ParticipantResult | null;
  round_id: number;
  stage_id: number;
  status: number;
};

export type BracketViewerData = {
  matchGames: [];
  matches: ViewerMatch[];
  participants: Array<{ id: number; name: string; tournament_id: number }>;
  stages: Array<{
    id: number;
    name: string;
    number: number;
    settings: { size: number };
    tournament_id: number;
    type: 'single_elimination';
  }>;
};

// brackets-model Status enum.
const STATUS_LOCKED = 0;
const STATUS_WAITING = 1;
const STATUS_READY = 2;
const STATUS_COMPLETED = 4;

const STAGE_ID = 1;
const GROUP_ID = 1;

type AnyMatch = OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;

/**
 * brackets-viewer infers the connectors from the position of a match inside its round, so the
 * matches of every round are ordered by the round-1 slot their competitors come from.
 */
function orderRounds(rounds: OpenApi.RoundWithMatches[]) {
  const positionByMatchId = new Map<number, number>();

  return rounds.map((round) => {
    const ordered = [...round.matches].sort((left, right) => {
      const leftOrigin = originPosition(left, positionByMatchId);
      const rightOrigin = originPosition(right, positionByMatchId);
      if (leftOrigin !== rightOrigin) return leftOrigin - rightOrigin;
      return left.id - right.id;
    });

    ordered.forEach((match, index) => positionByMatchId.set(match.id, index));
    return { matches: ordered, round };
  });
}

function originPosition(match: AnyMatch, positionByMatchId: Map<number, number>) {
  const origins = [
    match.stage_item_input1_winner_from_match_id,
    match.stage_item_input2_winner_from_match_id,
  ]
    .map((id) => (id == null ? undefined : positionByMatchId.get(id)))
    .filter((position): position is number => position != null);

  return origins.length > 0 ? Math.min(...origins) : Number.MAX_SAFE_INTEGER;
}

function toOpponent(
  inputId: number | null,
  score: number,
  known: Set<number>,
  showScore: boolean,
  result: ParticipantResult['result'],
): ParticipantResult {
  return {
    id: inputId != null && known.has(inputId) ? inputId : null,
    ...(showScore ? { score } : {}),
    ...(result ? { result } : {}),
  };
}

export function toBracketViewerData(
  stageItem: OpenApi.StageItemWithRounds,
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>,
  tournamentId: number,
): BracketViewerData | null {
  const participants = stageItem.inputs
    .map((input) => ({
      id: input.id,
      name: inputLabel(input, stageItemsById),
      tournament_id: tournamentId,
    }))
    .filter((participant) => participant.name !== 'TBD');
  const known = new Set(participants.map((participant) => participant.id));

  const matches: ViewerMatch[] = [];

  orderRounds(stageItem.rounds).forEach(({ matches: roundMatches }, roundIndex) => {
    roundMatches.forEach((match, matchIndex) => {
      const scored = isScored(match);
      const first = match.stage_item_input1_score;
      const second = match.stage_item_input2_score;
      const hasBoth = match.stage_item_input1_id != null && match.stage_item_input2_id != null;
      const hasNone = match.stage_item_input1_id == null && match.stage_item_input2_id == null;

      matches.push({
        child_count: 0,
        group_id: GROUP_ID,
        id: match.id,
        number: matchIndex + 1,
        opponent1: toOpponent(
          match.stage_item_input1_id,
          first,
          known,
          scored,
          scored ? (first === second ? 'draw' : first > second ? 'win' : 'loss') : undefined,
        ),
        opponent2: toOpponent(
          match.stage_item_input2_id,
          second,
          known,
          scored,
          scored ? (first === second ? 'draw' : second > first ? 'win' : 'loss') : undefined,
        ),
        round_id: roundIndex + 1,
        stage_id: STAGE_ID,
        status: scored
          ? STATUS_COMPLETED
          : hasBoth
            ? STATUS_READY
            : hasNone
              ? STATUS_LOCKED
              : STATUS_WAITING,
      });
    });
  });

  if (matches.length === 0) return null;

  return {
    matchGames: [],
    matches,
    participants,
    stages: [
      {
        id: STAGE_ID,
        name: stageItem.name || stageItem.type_name,
        number: 1,
        settings: { size: stageItem.team_count },
        tournament_id: tournamentId,
        type: 'single_elimination',
      },
    ],
  };
}

export function roundLabel(roundNumber: number, roundCount: number) {
  const fromFinal = roundCount - roundNumber;
  if (fromFinal === 0) return 'Final';
  if (fromFinal === 1) return 'Semi-finals';
  if (fromFinal === 2) return 'Quarter-finals';
  return `Round of ${2 ** (fromFinal + 1)}`;
}
