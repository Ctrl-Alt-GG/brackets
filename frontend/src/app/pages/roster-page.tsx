import { Navigate } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  BulkPlayersForm,
  DeleteTeamButton,
  FilterBox,
  membershipsByPlayer,
  NewPlayerForm,
  NewTeamForm,
  PlayerForm,
  TeamForm,
  useFilter,
  usePool,
  type Pool,
} from '../components/roster-editors';
import { getErrorMessage } from '../errors';
import { useSession } from '../hooks';
import { useOrganizerTranslation } from '../organizer-locales';
import { Disclosure, ErrorState, LoadingState, PageShell, Surface, SurfaceHeading } from '../ui';
import { loginPath, teamLogoUrl } from '../urls';
import { cx } from '../utils';

function PlayersList({ pool }: { pool: Pool }) {
  const { t } = useOrganizerTranslation();
  const filter = useFilter(pool.players, ['name']);
  const memberships = membershipsByPlayer(pool.teams);

  return (
    <>
      {pool.players.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('roster.noPlayers')}</p>
      ) : (
        <FilterBox
          label={t('roster.searchPlayers')}
          onChange={filter.setQuery}
          value={filter.query}
        />
      )}
      {filter.nothingMatches ? (
        <p className="text-sm text-base-content/70">
          {t('roster.noPlayerMatches', { query: filter.term })}
        </p>
      ) : null}
      <div className="space-y-3">
        {pool.players.map((player) => {
          const teams = (memberships.get(player.id) ?? []).map((membership) =>
            membership.active
              ? membership.team.name
              : t('roster.inactiveName', { name: membership.team.name }),
          );
          return (
            <Disclosure
              className={cx(
                'collapse collapse-arrow border border-base-300 bg-base-100/50',
                !filter.isShown(player) && 'hidden',
              )}
              key={player.id}
              summary={
                <>
                  <span className="font-semibold">{player.name}</span>
                  <span className="block text-sm text-base-content/70">
                    {teams.join(', ') || t('roster.inNoTeam')}
                  </span>
                </>
              }
            >
              <PlayerForm player={player} />
            </Disclosure>
          );
        })}
      </div>
    </>
  );
}

function TeamEditor({
  hidden,
  pool,
  team,
}: {
  hidden: boolean;
  pool: Pool;
  team: OpenApi.TeamWithMembers;
}) {
  const { t } = useOrganizerTranslation();
  const logoUrl = teamLogoUrl(team);
  const tournaments = team.participations.map((participation) => participation.tournament_name);

  return (
    <Disclosure
      className={cx(
        'collapse collapse-arrow border border-base-300 bg-base-100/50',
        hidden && 'hidden',
      )}
      summary={
        <>
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {logoUrl ? (
              <img alt="" className="size-6 shrink-0 rounded-field object-contain" src={logoUrl} />
            ) : null}
            {team.name}
          </span>
          <span className="block text-sm text-base-content/70">
            {team.members
              .map((member) =>
                member.active
                  ? member.player.name
                  : t('roster.inactiveName', { name: member.player.name }),
              )
              .join(', ') || t('roster.noTeamPlayers')}
          </span>
          {tournaments.length > 0 ? (
            <span className="block text-sm text-base-content/70">
              {t('roster.takesPartIn', { tournaments: tournaments.join(', ') })}
            </span>
          ) : null}
        </>
      }
    >
      <TeamForm pool={pool} team={team} />
      <div className="collapse-content border-t border-base-300 pt-4">
        {tournaments.length > 0 ? (
          <p className="text-sm text-base-content/70">{t('roster.deleteAfterLeaving')}</p>
        ) : (
          <DeleteTeamButton team={team} />
        )}
      </div>
    </Disclosure>
  );
}

function TeamsList({ pool }: { pool: Pool }) {
  const { t } = useOrganizerTranslation();
  const filter = useFilter(pool.teams, ['name', 'members.*.player.name']);

  return (
    <>
      {pool.teams.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('roster.noTeams')}</p>
      ) : (
        <FilterBox
          label={t('roster.searchTeams')}
          onChange={filter.setQuery}
          value={filter.query}
        />
      )}
      {filter.nothingMatches ? (
        <p className="text-sm text-base-content/70">
          {t('roster.noTeamMatches', { query: filter.term })}
        </p>
      ) : null}
      <div className="space-y-3">
        {pool.teams.map((team) => (
          <TeamEditor hidden={!filter.isShown(team)} key={team.id} pool={pool} team={team} />
        ))}
      </div>
    </>
  );
}

/**
 * The teams and players that every tournament shares. A tournament's Teams page lets them take
 * part, and changes made here reach every tournament they play in.
 */
export function RosterPage() {
  const { t } = useOrganizerTranslation();
  const [session] = useSession();
  const { error, pool, refetch } = usePool({ enabled: Boolean(session) });

  if (!session) {
    return <Navigate replace to={loginPath('/roster')} />;
  }

  return (
    <PageShell title={t('rosterPage.title')}>
      <p className="max-w-3xl text-sm text-base-content/80">{t('rosterPage.intro')}</p>
      {pool ? (
        <div className="grid items-start gap-6 xl:grid-cols-2">
          <Surface>
            <SurfaceHeading
              actions={
                <span className="text-sm text-base-content/70">
                  {t('roster.playerCount', { count: pool.players.length })}
                </span>
              }
              title={t('roster.players')}
            />
            <NewPlayerForm />
            <div className="border-t border-base-300 pt-4">
              <BulkPlayersForm />
            </div>
            <div className="space-y-3 border-t border-base-300 pt-4">
              <PlayersList pool={pool} />
            </div>
          </Surface>
          <Surface>
            <SurfaceHeading
              actions={
                <span className="text-sm text-base-content/70">
                  {t('roster.teamCount', { count: pool.teams.length })}
                </span>
              }
              title={t('roster.teams')}
            />
            <NewTeamForm pool={pool} />
            <div className="space-y-3 border-t border-base-300 pt-4">
              <TeamsList pool={pool} />
            </div>
          </Surface>
        </div>
      ) : error ? (
        <ErrorState
          action={
            <button className="btn btn-sm" onClick={() => void refetch()} type="button">
              {t('common.retry')}
            </button>
          }
          error={getErrorMessage(error)}
          title={t('rosterPage.loadFailed')}
        />
      ) : (
        <LoadingState title={t('rosterPage.loading')} />
      )}
    </PageShell>
  );
}
