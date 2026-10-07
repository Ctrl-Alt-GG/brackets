import { Link, useNavigate } from 'react-router';

import * as OpenApi from '../../openapi';
import { toBracketViewerData } from '../bracket-adapter';
import { BracketViewer } from '../components/bracket-viewer';
import { teamPath, useTournamentContext } from '../tournament-context';
import { hasTeam, isBracket } from '../utils';
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
  const navigate = useNavigate();
  const { publicPath } = useTournamentContext();
  const brackets = stages.flatMap((stage) =>
    stage.stage_items.filter(isBracket).map((stageItem) => ({ stage, stageItem })),
  );

  if (brackets.length === 0) return null;

  return (
    <Surface className="space-y-6">
      <SurfaceHeading
        actions={
          bigScreenPath ? (
            <Link className="btn btn-ghost btn-sm" to={bigScreenPath}>
              Big screen
            </Link>
          ) : null
        }
        title={brackets.length === 1 ? 'Bracket' : 'Brackets'}
      />
      {brackets.map(({ stage, stageItem }) => {
        const data = toBracketViewerData(stageItem, stageItemsById, tournamentId);
        const teamParticipants = new Map(
          stageItem.inputs.filter(hasTeam).map((input) => [input.id, input.team_id] as const),
        );

        return (
          <section
            className="scroll-mt-6 space-y-3"
            id={`stage-item-${stageItem.id}`}
            key={stageItem.id}
          >
            <div>
              <h3 className="text-lg font-semibold">{stageItem.name || stageItem.type_name}</h3>
              <p className="text-sm text-base-content/70">
                {stage.name} · {stageItem.team_count} teams
              </p>
            </div>
            {data ? (
              <BracketViewer
                data={data}
                onTeamClick={(teamId) => navigate(teamPath(publicPath, teamId))}
                teamParticipants={teamParticipants}
              />
            ) : (
              <p className="text-sm text-base-content/70">
                The bracket appears here once the matches have been drawn.
              </p>
            )}
          </section>
        );
      })}
    </Surface>
  );
}
