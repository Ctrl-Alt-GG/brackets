import { useState } from 'react';

import * as OpenApi from '../../openapi';
import { StageItemVisualization } from './tournament-overview';
import type { TournamentBundle } from '../types';
import { cx } from '../utils';
import { Surface } from '../ui';

export function BracketSection({
  bundle,
  stageItemsById,
  teamMap,
}: {
  bundle: TournamentBundle;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  const stageItems = bundle.stages.flatMap((stage) =>
    stage.stage_items.map((stageItem) => ({ stage, stageItem })),
  );
  const [selectedId, setSelectedId] = useState<number | null>(stageItems[0]?.stageItem.id ?? null);
  const selected =
    stageItems.find((entry) => entry.stageItem.id === selectedId) ?? stageItems[0] ?? null;

  if (!selected) {
    return (
      <Surface>
        <p className="text-sm text-zinc-400">
          Nothing to show yet — the tournament format has not been set up.
        </p>
      </Surface>
    );
  }

  return (
    <Surface className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
          Follow the road to the final
        </p>
        <h2 className="mt-2 font-display text-2xl font-semibold text-white">Brackets and groups</h2>
      </div>
      {stageItems.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {stageItems.map(({ stage, stageItem }) => (
            <button
              className={cx(
                'rounded-full px-4 py-2 text-sm font-semibold transition',
                stageItem.id === selected.stageItem.id
                  ? 'bg-brand-600 text-white'
                  : 'bg-white/10 text-zinc-200 hover:bg-white/20',
              )}
              key={stageItem.id}
              onClick={() => setSelectedId(stageItem.id)}
              type="button"
            >
              {stage.name} · {stageItem.name || stageItem.type_name}
            </button>
          ))}
        </div>
      ) : null}
      <StageItemVisualization
        stageItem={selected.stageItem}
        stageItemsById={stageItemsById}
        teamMap={teamMap}
        tournamentId={bundle.tournament.id}
      />
    </Surface>
  );
}
