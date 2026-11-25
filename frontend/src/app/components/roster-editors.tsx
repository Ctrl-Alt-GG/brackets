/*
 * Editing the teams and players that every tournament shares. The Teams and players page and a
 * tournament's Teams page both use these, so a change made in either looks the same.
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { matchSorter } from 'match-sorter';
import { useMemo, useState } from 'react';
import { useWatch, type Control, type UseFormRegisterReturn } from 'react-hook-form';
import { z } from 'zod';

import * as OpenApi from '../../openapi';
import {
  createPlayerApiPlayersPostMutation,
  createPlayersApiPlayersMultiPostMutation,
  createTeamApiTeamsPostMutation,
  deletePlayerApiPlayersPlayerIdDeleteMutation,
  deleteTeamApiTeamsTeamIdDeleteMutation,
  getAllPlayersApiPlayersGetOptions,
  getTeamsApiTeamsGetOptions,
  renamePlayerApiPlayersPlayerIdPutMutation,
  updateTeamApiTeamsTeamIdPutMutation,
  updateTeamLogoApiTeamsTeamIdLogoPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zPlayerBody, zPlayerMultiBody, zTeamBody } from '../../openapi/zod.gen';
import { confirm } from '../confirm';
import { useCreateForm } from '../create-form';
import { useOrganizerTranslation } from '../organizer-locales';
import { useSavedForm } from '../saved-form';
import { Field, SaveButton } from '../ui';
import { teamLogoUrl } from '../urls';
import { cx, groupBy } from '../utils';
import { LogoField } from './logo-field';

/**
 * Narrows a long list down to what was typed. The rows that don't match are hidden, not removed:
 * an editor that is open keeps what was typed into it, and a ticked box stays ticked.
 */
export function useFilter<T extends { id: number }>(items: T[], keys: string[]) {
  const [query, setQuery] = useState('');
  const term = query.trim();
  const matching = term ? new Set(matchSorter(items, term, { keys }).map((item) => item.id)) : null;

  return {
    isShown: (item: T) => matching?.has(item.id) ?? true,
    nothingMatches: matching?.size === 0,
    query,
    setQuery,
    term,
  };
}

export function FilterBox({
  className,
  label,
  onChange,
  value,
}: {
  className?: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <input
      aria-label={label}
      className={cx('input w-full sm:max-w-md', className)}
      onChange={(event) => onChange(event.target.value)}
      // Inside a form, Enter would save it.
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.preventDefault();
      }}
      placeholder={label}
      type="search"
      value={value}
    />
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  const { t } = useOrganizerTranslation();
  return active ? (
    <span className="badge badge-soft badge-success badge-sm">{t('common.active')}</span>
  ) : (
    <span className="badge badge-soft badge-sm">{t('common.inactive')}</span>
  );
}

/** The players and teams that every tournament shares. */
export type Pool = {
  players: OpenApi.Player[];
  teams: OpenApi.TeamWithMembers[];
};

/** Loads the pool, for an organizer who is signed in. `pool` is there once both lists are. */
export function usePool({ enabled = true }: { enabled?: boolean } = {}) {
  const teams = useQuery({ ...getTeamsApiTeamsGetOptions(), enabled });
  const players = useQuery({ ...getAllPlayersApiPlayersGetOptions(), enabled });
  const pool: Pool | undefined =
    teams.data && players.data ? { players: players.data.data, teams: teams.data.data } : undefined;

  return {
    error: teams.error ?? players.error,
    pool,
    refetch: () => Promise.all([teams.refetch(), players.refetch()]),
  };
}

/** The teams each player is a member of, by player id. */
export function membershipsByPlayer(teams: OpenApi.TeamWithMembers[]) {
  return groupBy(
    teams.flatMap((team) =>
      team.members.map((member) => ({ active: member.active, playerId: member.player.id, team })),
    ),
    (membership) => membership.playerId,
  );
}

/** Long enough that looking for a name by eye takes a while. */
const SEARCHABLE_PLAYER_COUNT = 12;

// Checkboxes hold their values as strings. Members are active unless they are marked inactive.
const teamSchema = z
  .object({
    inactive_ids: z.array(z.coerce.number().int()),
    name: zTeamBody.shape.name,
    player_ids: z.array(z.coerce.number().int()),
  })
  .transform(({ inactive_ids, name, player_ids }): OpenApi.TeamBody => ({
    members: player_ids.map((player_id) => ({
      active: !inactive_ids.includes(player_id),
      player_id,
    })),
    name,
  }));

type TeamFormValues = z.input<typeof teamSchema>;

function teamFormValues(team?: OpenApi.TeamWithMembers): TeamFormValues {
  return {
    inactive_ids: (team?.members ?? [])
      .filter((member) => !member.active)
      .map((member) => String(member.player.id)),
    name: team?.name ?? '',
    player_ids: (team?.members ?? []).map((member) => String(member.player.id)),
  };
}

/**
 * The players to pick a team's members from, each with the teams they are in already. A member
 * can be marked inactive: they stay in the roster but don't play for the team. A player plays for
 * one team at most among the teams of a tournament.
 */
function MemberChecklist({
  control,
  members,
  inactive,
  pool,
  team,
}: {
  control: Control<TeamFormValues, unknown, OpenApi.TeamBody>;
  members: UseFormRegisterReturn<'player_ids'>;
  inactive: UseFormRegisterReturn<'inactive_ids'>;
  pool: Pool;
  /** The team being edited. A new team has none. */
  team?: OpenApi.TeamWithMembers;
}) {
  const { t } = useOrganizerTranslation();
  const filter = useFilter(pool.players, ['name']);
  const checked = new Set(useWatch({ control, name: 'player_ids' }));
  const memberships = useMemo(() => membershipsByPlayer(pool.teams), [pool.teams]);
  // The team's members come first: in a big pool they would be hard to find otherwise.
  const currentMembers = new Set(team?.members.map((member) => member.player.id));
  const ordered = pool.players.toSorted(
    (left, right) => Number(currentMembers.has(right.id)) - Number(currentMembers.has(left.id)),
  );

  return (
    <fieldset className="fieldset">
      <legend className="fieldset-legend">{t('roster.members')}</legend>
      {pool.players.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('roster.addPlayersFirst')}</p>
      ) : (
        <>
          {pool.players.length >= SEARCHABLE_PLAYER_COUNT ? (
            <FilterBox
              className="sm:max-w-none"
              label={t('roster.searchPlayers')}
              onChange={filter.setQuery}
              value={filter.query}
            />
          ) : null}
          {filter.nothingMatches ? (
            <p className="text-sm text-base-content/70">
              {t('roster.noPlayerMatches', { query: filter.term })}
            </p>
          ) : null}
          <div className="grid max-h-72 gap-2 overflow-y-auto rounded-box border border-base-300 bg-base-100/40 p-3 sm:grid-cols-2">
            {ordered.map((player) => {
              const elsewhere = (memberships.get(player.id) ?? [])
                .filter((membership) => membership.active && membership.team.id !== team?.id)
                .map((membership) => membership.team.name);
              const isMember = checked.has(String(player.id));
              return (
                <div
                  className={cx(
                    'flex items-start gap-3 text-sm',
                    !filter.isShown(player) && 'hidden',
                  )}
                  key={player.id}
                >
                  <label className="flex flex-1 cursor-pointer items-start gap-3">
                    <input
                      className="checkbox checkbox-primary checkbox-sm"
                      type="checkbox"
                      value={player.id}
                      {...members}
                    />
                    <span>
                      {player.name}
                      {elsewhere.length > 0 ? (
                        <span className="block text-xs text-base-content/70">
                          {t('roster.playsFor', { teams: elsewhere.join(', ') })}
                        </span>
                      ) : null}
                    </span>
                  </label>
                  {isMember ? (
                    <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-base-content/80">
                      <input
                        className="checkbox checkbox-xs"
                        type="checkbox"
                        value={player.id}
                        {...inactive}
                      />
                      {t('common.inactive')}
                    </label>
                  ) : null}
                </div>
              );
            })}
          </div>
          <p className="label whitespace-normal">{t('roster.oneTeamPerTournament')}</p>
        </>
      )}
    </fieldset>
  );
}

export function NewTeamForm({ pool }: { pool: Pool }) {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm<TeamFormValues, unknown, OpenApi.TeamBody>({
    defaultValues: teamFormValues(),
    resolver: zodResolver(teamSchema),
  });
  const create = useMutation({
    ...createTeamApiTeamsPostMutation(),
    meta: { successMessage: t('roster.teamCreated') },
  });

  return (
    <form onSubmit={form.submitWith((body) => create.mutateAsync({ body }))}>
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.name?.message} label={t('roster.teamName')}>
          <input
            className="input w-full"
            placeholder="Arcade Wolves"
            required
            {...form.register('name')}
          />
        </Field>
        <MemberChecklist
          control={form.control}
          inactive={form.register('inactive_ids')}
          members={form.register('player_ids')}
          pool={pool}
        />
        <button className="btn btn-primary mt-4" type="submit">
          {t('roster.createTeam')}
        </button>
      </fieldset>
    </form>
  );
}

/**
 * A team's name, logo and roster. They are the same in every tournament the team plays in, which
 * the form says when there is more than one.
 */
export function TeamForm({ pool, team }: { pool: Pool; team: OpenApi.TeamWithMembers }) {
  const { t } = useOrganizerTranslation();
  const form = useSavedForm<TeamFormValues, unknown, OpenApi.TeamBody>({
    resolver: zodResolver(teamSchema),
    values: teamFormValues(team),
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateTeamApiTeamsTeamIdPutMutation(),
    meta: { successMessage: t('roster.teamSaved') },
  });
  const uploadLogo = useMutation({
    ...updateTeamLogoApiTeamsTeamIdLogoPostMutation(),
    meta: { successMessage: t('common.logoUpdated') },
  });
  const path = { team_id: team.id };
  const tournaments = team.participations.map((participation) => participation.tournament_name);

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      {tournaments.length > 1 ? (
        <p className="text-sm text-base-content/70">
          {t('roster.sharedTeam', { tournaments: tournaments.join(', ') })}
        </p>
      ) : null}
      <Field error={form.formState.errors.name?.message} label={t('roster.teamName')}>
        <input className="input w-full" required {...form.register('name')} />
      </Field>
      <LogoField
        isPending={uploadLogo.isPending}
        label={t('roster.teamLogo')}
        logoUrl={teamLogoUrl(team)}
        onChange={(file) => uploadLogo.mutate({ body: { file }, path })}
      />
      <MemberChecklist
        control={form.control}
        inactive={form.register('inactive_ids')}
        members={form.register('player_ids')}
        pool={pool}
        team={team}
      />
      <SaveButton className="mt-4" dirty={form.formState.isDirty} disabled={update.isPending}>
        {t('roster.saveTeam')}
      </SaveButton>
    </form>
  );
}

/** Deleting a team, which only a team that takes part in no tournament can be. */
export function DeleteTeamButton({ team }: { team: OpenApi.TeamWithMembers }) {
  const { t } = useOrganizerTranslation();
  const remove = useMutation({
    ...deleteTeamApiTeamsTeamIdDeleteMutation(),
    meta: { successMessage: t('roster.teamDeleted') },
  });

  return (
    <button
      className="btn btn-error btn-soft"
      disabled={remove.isPending}
      onClick={async () => {
        if (
          await confirm({
            confirmLabel: t('roster.deleteTeam'),
            destructive: true,
            message: t('roster.deleteQuestion', { name: team.name }),
          })
        ) {
          remove.mutate({ path: { team_id: team.id } });
        }
      }}
      type="button"
    >
      {t('roster.deleteTeam')}
    </button>
  );
}

export function NewPlayerForm() {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm({
    defaultValues: { name: '' },
    resolver: zodResolver(zPlayerBody),
  });
  const create = useMutation({
    ...createPlayerApiPlayersPostMutation(),
    meta: { successMessage: t('roster.playerAdded') },
  });

  return (
    <form onSubmit={form.submitWith((body) => create.mutateAsync({ body }))}>
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.name?.message} label={t('roster.playerName')}>
          <input
            className="input w-full"
            placeholder="Mortal Kombat main"
            required
            {...form.register('name')}
          />
        </Field>
        <button className="btn btn-primary mt-4" type="submit">
          {t('roster.addPlayer')}
        </button>
      </fieldset>
    </form>
  );
}

export function BulkPlayersForm() {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm({
    defaultValues: { names: '' },
    resolver: zodResolver(zPlayerMultiBody),
  });
  const create = useMutation({
    ...createPlayersApiPlayersMultiPostMutation(),
    meta: { successMessage: t('roster.playersAdded') },
  });

  return (
    <form onSubmit={form.submitWith((body) => create.mutateAsync({ body }))}>
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.names?.message} label={t('roster.bulkNames')}>
          <textarea
            className="textarea min-h-28 w-full"
            placeholder={t('roster.onePlayerPerLine')}
            {...form.register('names')}
          />
        </Field>
        <button className="btn btn-soft mt-4" type="submit">
          {t('roster.bulkImport')}
        </button>
      </fieldset>
    </form>
  );
}

/** A player's name, which is the same in every team and tournament. */
export function PlayerForm({ player }: { player: OpenApi.Player }) {
  const { t } = useOrganizerTranslation();
  const form = useSavedForm({
    resolver: zodResolver(zPlayerBody),
    values: { name: player.name },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...renamePlayerApiPlayersPlayerIdPutMutation(),
    meta: { successMessage: t('roster.playerSaved') },
  });
  const remove = useMutation({
    ...deletePlayerApiPlayersPlayerIdDeleteMutation(),
    meta: { successMessage: t('roster.playerDeleted') },
  });
  const path = { player_id: player.id };

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <Field error={form.formState.errors.name?.message} label={t('common.name')}>
        <input className="input w-full" required {...form.register('name')} />
      </Field>
      <div className="mt-4 flex flex-wrap gap-2">
        <SaveButton dirty={form.formState.isDirty} disabled={update.isPending}>
          {t('common.save')}
        </SaveButton>
        <button
          className="btn btn-error btn-soft"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: t('roster.deletePlayer'),
                destructive: true,
                message: t('roster.deletePlayerQuestion', { name: player.name }),
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          {t('common.delete')}
        </button>
      </div>
    </form>
  );
}
