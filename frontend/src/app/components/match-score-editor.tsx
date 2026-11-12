import { lazy, Suspense } from 'react';

import * as OpenApi from '../../openapi';
import type { FlattenedMatch } from '../types';
import { inputLabel, inputTeamId, isBracket } from '../utils';

// Only organizers enter results, so the form and its validation load when one of them needs it.
const ScoreForm = lazy(() =>
  import('./score-form').then((module) => ({ default: module.ScoreForm })),
);

/** The result of a match, to be entered where the organizer is looking at the match. */
export function MatchScoreEditor({
  entry,
  stageItemsById,
  tournamentId,
}: {
  entry: FlattenedMatch;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentId: number;
}) {
  return (
    <Suspense fallback={<span className="loading loading-spinner loading-sm" />}>
      <ScoreForm
        allowsDraw={!isBracket(entry.stageItem)}
        key={`${entry.match.id}:${inputTeamId(entry.match.stage_item_input1)}:${inputTeamId(entry.match.stage_item_input2)}`}
        label1={inputLabel(entry.match.stage_item_input1, stageItemsById)}
        label2={inputLabel(entry.match.stage_item_input2, stageItemsById)}
        match={entry.match}
        tournamentId={tournamentId}
      />
    </Suspense>
  );
}
