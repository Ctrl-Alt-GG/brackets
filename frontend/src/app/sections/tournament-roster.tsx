/*
 * A tournament's teams and players. Teams take part from the pool that every tournament shares,
 * and their active members play for them here: the tournament's lineup.
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router';
import { z } from 'zod';

import * as OpenApi from '../../openapi';
import {
  addTournamentTeamsApiTournamentsTournamentIdTeamsPostMutation,
  createTournamentTeamsApiTournamentsTournamentIdTeamsMultiPostMutation,
  removeTournamentTeamApiTournamentsTournamentIdTeamsTeamIdDeleteMutation,
  updateTournamentTeamApiTournamentsTournamentIdTeamsTeamIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zTeamMultiBody } from '../../openapi/zod.gen';
import {
  ActiveBadge,
  FilterBox,
  TeamForm,
  useFilter,
  usePool,
  type Pool,
} from '../components/roster-editors';
import { confirm } from '../confirm';
import { useCreateForm } from '../create-form';
import { getErrorMessage } from '../errors';
import { useOrganizerTranslation } from '../organizer-locales';
import type { TournamentBundle } from '../types';
import { Disclosure, ErrorState, Field, LoadingState, Surface, SurfaceHeading } from '../ui';
import { teamLogoUrl } from '../urls';
import { cx } from '../utils';

/** Who plays in the tournament, for which team, and how they have done so far. */
export function PlayersSection({ bundle }: { bundle: TournamentBundle }) {
  const { t } = useOrganizerTranslation();
  const filter = useFilter(bundle.players, ['name']);
  const teamNames = new Map(bundle.teams.map((team) => [team.id, team.name]));

  return (
    <Surface>
      <SurfaceHeading
        actions={
          <span className="text-sm text-base-content/70">
            {t('roster.playerCount', { count: bundle.players.length })}
          </span>
        }
        title={t('roster.players')}
      />
      <p className="text-sm text-base-content/70">
        {t('lineup.help')}{' '}
        <Link className="link" to="/roster">
          {t('lineup.manage')}
        </Link>
      </p>
      {bundle.players.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('lineup.empty')}</p>
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
      <ul className="divide-y divide-base-300 rounded-box border border-base-300">
        {bundle.players.map((player) => (
          <li
            className={cx(
              'flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3',
              !filter.isShown(player) && 'hidden',
            )}
            key={player.id}
          >
            <span>
              <span className="font-medium">{player.name}</span>
              <span className="text-sm text-base-content/70">
                {' '}
                · {teamNames.get(player.team_id)}
              </span>
            </span>
            <span className="text-sm text-base-content/70">
              {t('roster.playerRecord', {
                draws: player.draws,
                elo: player.elo_score,
                losses: player.losses,
                wins: player.wins,
              })}
            </span>
          </li>
        ))}
      </ul>
    </Surface>
  );
}

// Checkboxes hold their values as strings.
const addTeamsSchema = z.object({ team_ids: z.array(z.coerce.number().int()).min(1) });

/** Teams from the pool that don't take part yet. */
function AddTeamsForm({ pool, tournament }: { pool: Pool; tournament: OpenApi.Tournament }) {
  const { t } = useOrganizerTranslation();
  const candidates = pool.teams.filter(
    (team) =>
      !team.participations.some((participation) => participation.tournament_id === tournament.id),
  );
  const filter = useFilter(candidates, ['name', 'members.*.player.name']);
  const form = useCreateForm<z.input<typeof addTeamsSchema>, unknown, OpenApi.TournamentTeamsBody>({
    defaultValues: { team_ids: [] },
    resolver: zodResolver(addTeamsSchema),
  });
  const add = useMutation({
    ...addTournamentTeamsApiTournamentsTournamentIdTeamsPostMutation(),
    meta: { successMessage: t('participation.added') },
  });

  if (candidates.length === 0) {
    return (
      <p className="text-sm text-base-content/70">
        {pool.teams.length === 0 ? t('participation.noTeamsYet') : t('participation.allTakePart')}{' '}
        <Link className="link" to="/roster">
          {t('lineup.manage')}
        </Link>
      </p>
    );
  }

  return (
    <form
      onSubmit={form.submitWith((body) =>
        add.mutateAsync({ body, path: { tournament_id: tournament.id } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <FilterBox
          className="sm:max-w-none"
          label={t('roster.searchTeams')}
          onChange={filter.setQuery}
          value={filter.query}
        />
        <div className="mt-3 grid max-h-72 gap-2 overflow-y-auto rounded-box border border-base-300 bg-base-100/40 p-3 sm:grid-cols-2">
          {candidates.map((team) => (
            <label
              className={cx(
                'flex cursor-pointer items-start gap-3 text-sm',
                !filter.isShown(team) && 'hidden',
              )}
              key={team.id}
            >
              <input
                className="checkbox checkbox-primary checkbox-sm"
                type="checkbox"
                value={team.id}
                {...form.register('team_ids')}
              />
              <span>
                {team.name}
                <span className="block text-xs text-base-content/70">
                  {team.members
                    .filter((member) => member.active)
                    .map((member) => member.player.name)
                    .join(', ') || t('roster.noTeamPlayers')}
                </span>
              </span>
            </label>
          ))}
        </div>
        {form.formState.errors.team_ids ? (
          <p className="label text-error">{t('participation.pickTeams')}</p>
        ) : null}
        <button className="btn btn-primary mt-4" type="submit">
          {add.isPending ? t('common.adding') : t('participation.add')}
        </button>
      </fieldset>
    </form>
  );
}

function BulkTeamsForm({ tournamentId }: { tournamentId: number }) {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm({
    defaultValues: { names: '' },
    resolver: zodResolver(zTeamMultiBody),
  });
  const create = useMutation({
    ...createTournamentTeamsApiTournamentsTournamentIdTeamsMultiPostMutation(),
    meta: { successMessage: t('roster.teamsCreated') },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field
          error={form.formState.errors.names?.message}
          hint={t('roster.teamListHint')}
          label={t('roster.teamNames')}
        >
          <textarea
            className="textarea min-h-28 w-full"
            placeholder={t('roster.teamList')}
            {...form.register('names')}
          />
        </Field>
        <button className="btn btn-soft mt-4" type="submit">
          {t('roster.createFromList')}
        </button>
      </fieldset>
    </form>
  );
}

/** Whether the team plays the rounds still to come, and taking it out of the tournament. */
function Participation({
  team,
  tournamentId,
}: {
  team: OpenApi.TournamentTeamWithPlayers;
  tournamentId: number;
}) {
  const { t } = useOrganizerTranslation();
  const path = { team_id: team.id, tournament_id: tournamentId };
  const setActive = useMutation({
    ...updateTournamentTeamApiTournamentsTournamentIdTeamsTeamIdPutMutation(),
    meta: { successMessage: t('participation.saved') },
  });
  const remove = useMutation({
    ...removeTournamentTeamApiTournamentsTournamentIdTeamsTeamIdDeleteMutation(),
    meta: { successMessage: t('participation.removed') },
  });

  return (
    <div className="collapse-content space-y-3 border-t border-base-300 pt-4">
      <p className="text-sm text-base-content/70">
        {team.active ? t('participation.activeHelp') : t('participation.inactiveHelp')}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          className="btn btn-soft btn-sm"
          disabled={setActive.isPending}
          onClick={() => setActive.mutate({ body: { active: !team.active }, path })}
          type="button"
        >
          {team.active ? t('participation.deactivate') : t('participation.activate')}
        </button>
        <button
          className="btn btn-error btn-soft btn-sm"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: t('participation.remove'),
                destructive: true,
                message: t('participation.removeQuestion', { name: team.name }),
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          {t('participation.remove')}
        </button>
      </div>
    </div>
  );
}

/**
 * A team of the tournament: the team itself, which every tournament shares, and its participation
 * here.
 */
function TournamentTeamEditor({
  hidden,
  pool,
  poolFailed,
  team,
  tournamentId,
}: {
  hidden: boolean;
  /** The shared teams and players, once they have loaded. */
  pool: Pool | undefined;
  /** Loading the pool failed. The page offers to try again. */
  poolFailed: boolean;
  team: OpenApi.TournamentTeamWithPlayers;
  tournamentId: number;
}) {
  const { t } = useOrganizerTranslation();
  const logoUrl = teamLogoUrl(team);
  const shared = pool?.teams.find((candidate) => candidate.id === team.id);

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
            <ActiveBadge active={team.active} />
          </span>
          <span className="block text-sm text-base-content/70">
            {team.players.map((player) => player.name).join(', ') || t('roster.noTeamPlayers')}
          </span>
        </>
      }
    >
      {shared && pool ? (
        <TeamForm pool={pool} team={shared} />
      ) : (
        <p className="collapse-content text-sm text-base-content/70" role="status">
          {poolFailed ? t('rosterPage.loadFailed') : t('rosterPage.loading')}
        </p>
      )}
      <Participation team={team} tournamentId={tournamentId} />
    </Disclosure>
  );
}

export function TeamsSection({ bundle }: { bundle: TournamentBundle }) {
  const { t } = useOrganizerTranslation();
  const { error, pool, refetch } = usePool();
  const filter = useFilter(bundle.teams, ['name', 'players.*.name']);
  const tournamentId = bundle.tournament.id;

  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <SurfaceHeading title={t('participation.addTitle')} />
          {pool ? (
            <AddTeamsForm pool={pool} tournament={bundle.tournament} />
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
        </Surface>
        <Surface>
          <SurfaceHeading title={t('roster.batchTeams')} />
          <BulkTeamsForm tournamentId={tournamentId} />
        </Surface>
      </div>

      <Surface>
        <SurfaceHeading
          actions={
            <span className="text-sm text-base-content/70">
              {t('roster.teamCount', { count: bundle.teams.length })}
            </span>
          }
          title={t('participation.listTitle')}
        />
        {bundle.teams.length === 0 ? (
          <p className="text-sm text-base-content/70">{t('participation.none')}</p>
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
        <div className="grid items-start gap-3 lg:grid-cols-2">
          {bundle.teams.map((team) => (
            <TournamentTeamEditor
              hidden={!filter.isShown(team)}
              key={team.id}
              pool={pool}
              poolFailed={error != null}
              team={team}
              tournamentId={tournamentId}
            />
          ))}
        </div>
      </Surface>
    </div>
  );
}
