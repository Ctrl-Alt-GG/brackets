import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import * as OpenApi from '../../openapi';
import { toBracketViewerData } from '../bracket-adapter';
import { BracketViewer } from '../components/bracket-viewer';
import { teamPath, useTournamentContext } from '../tournament-context';
import { hasBracketView, hasTeam, isBracket, stageItemName, stageTypeName } from '../utils';
import { Surface, SurfaceHeading } from '../ui';

export function BracketSection({
  bigScreenPath,
  stages,
  stageItemsById,
  tournamentId,
}: {
  bigScreenPath?: string;
  stages: OpenApi.StageWithStageItems[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentId: number;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { isBigScreen, publicPath } = useTournamentContext();
  const brackets = stages.flatMap((stage) =>
    stage.stage_items.filter(hasBracketView).map((stageItem) => ({ stage, stageItem })),
  );

  if (brackets.length === 0) return null;

  return (
    <Surface className="space-y-6">
      <SurfaceHeading
        actions={
          bigScreenPath ? (
            <Link className="btn btn-ghost btn-sm" to={bigScreenPath}>
              {t('common.bigScreen')}
            </Link>
          ) : null
        }
        title={t('bracket.title', { count: brackets.length })}
      />
      {brackets.map(({ stage, stageItem }) => {
        const data = toBracketViewerData(stageItem, stageItemsById, tournamentId, t);
        // A screen at the venue is read from afar, and nobody clicks it: team names aren't links.
        const teamLinks = isBigScreen
          ? {}
          : {
              onTeamClick: (teamId: number) => navigate(teamPath(publicPath, teamId)),
              teamParticipants: new Map(
                stageItem.inputs.filter(hasTeam).map((input) => [input.id, input.team_id] as const),
              ),
            };

        return (
          <section
            className="scroll-mt-6 space-y-3"
            id={`stage-item-${stageItem.id}`}
            key={stageItem.id}
          >
            <div>
              <h3 className="text-lg font-semibold">{stageItemName(stageItem, t)}</h3>
              <p className="text-sm text-base-content/70">
                {stage.name} · {stageTypeName(stageItem, t)} ·{' '}
                {t('common.teamCount', { count: stageItem.team_count })}
              </p>
            </div>
            {data ? (
              <BracketViewer data={data} {...teamLinks} />
            ) : (
              <p className="text-sm text-base-content/70">
                {isBracket(stageItem) ? t('bracket.pendingKnockout') : t('bracket.pendingSwiss')}
              </p>
            )}
          </section>
        );
      })}
    </Surface>
  );
}
