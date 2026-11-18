import { useSavedForm } from '../saved-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { matchSorter } from 'match-sorter';
import { useMemo, useState } from 'react';
import { type UseFormRegisterReturn } from 'react-hook-form';
import { z } from 'zod';

import * as OpenApi from '../../openapi';
import {
  createMultiplePlayersApiTournamentsTournamentIdPlayersMultiPostMutation,
  createMultipleTeamsApiTournamentsTournamentIdTeamsMultiPostMutation,
  createSinglePlayerApiTournamentsTournamentIdPlayersPostMutation,
  createTeamApiTournamentsTournamentIdTeamsPostMutation,
  deletePlayerApiTournamentsTournamentIdPlayersPlayerIdDeleteMutation,
  deleteTeamApiTournamentsTournamentIdTeamsTeamIdDeleteMutation,
  updatePlayerByIdApiTournamentsTournamentIdPlayersPlayerIdPutMutation,
  updateTeamByIdApiTournamentsTournamentIdTeamsTeamIdPutMutation,
  updateTeamLogoApiTournamentsTournamentIdTeamsTeamIdLogoPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zPlayerBody, zPlayerMultiBody, zTeamBody, zTeamMultiBody } from '../../openapi/zod.gen';
import { LogoField } from '../components/logo-field';
import { useCreateForm } from '../create-form';
import type { TournamentBundle } from '../types';
import { CheckboxField, Disclosure, Field, Surface, SurfaceHeading } from '../ui';
import { teamLogoUrl } from '../urls';
import { cx, groupBy } from '../utils';
import { confirm } from '../confirm';

/**
 * Narrows a long list down to what was typed. The rows that don't match are hidden, not removed:
 * an editor that is open keeps what was typed into it, and a ticked box stays ticked.
 */
function useFilter<T extends { id: number }>(items: T[], keys: string[]) {
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

function FilterBox({
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

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="badge badge-soft badge-success badge-sm">Active</span>
  ) : (
    <span className="badge badge-soft badge-sm">Inactive</span>
  );
}

function NewPlayerForm({ tournamentId }: { tournamentId: number }) {
  const form = useCreateForm({
    defaultValues: { active: true, name: '' },
    resolver: zodResolver(zPlayerBody),
  });
  const create = useMutation({
    ...createSinglePlayerApiTournamentsTournamentIdPlayersPostMutation(),
    meta: { successMessage: 'Player added.' },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.name?.message} label="Player name">
          <input
            className="input w-full"
            placeholder="Mortal Kombat main"
            required
            {...form.register('name')}
          />
        </Field>
        <CheckboxField className="mt-3" label="Player is active" {...form.register('active')} />
        <button className="btn btn-primary mt-4" type="submit">
          Add player
        </button>
      </fieldset>
    </form>
  );
}

function BulkPlayersForm({ tournamentId }: { tournamentId: number }) {
  const form = useCreateForm({
    defaultValues: { active: true, names: '' },
    resolver: zodResolver(zPlayerMultiBody),
  });
  const create = useMutation({
    ...createMultiplePlayersApiTournamentsTournamentIdPlayersMultiPostMutation(),
    meta: { successMessage: 'Players added.' },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.names?.message} label="Bulk import names">
          <textarea
            className="textarea min-h-28 w-full"
            placeholder="One player per line"
            {...form.register('names')}
          />
        </Field>
        <button className="btn btn-soft mt-4" type="submit">
          Bulk import
        </button>
      </fieldset>
    </form>
  );
}

function PlayerEditor({
  hidden,
  player,
  tournamentId,
}: {
  hidden: boolean;
  player: OpenApi.Player;
  tournamentId: number;
}) {
  return (
    <Disclosure
      className={cx(
        'collapse collapse-arrow border border-base-300 bg-base-100/50',
        hidden && 'hidden',
      )}
      summary={
        <>
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {player.name}
            <ActiveBadge active={player.active} />
          </span>
          <span className="block text-sm text-base-content/70">
            {player.wins}W / {player.draws}D / {player.losses}L · ELO {player.elo_score}
          </span>
        </>
      }
    >
      <PlayerForm player={player} tournamentId={tournamentId} />
    </Disclosure>
  );
}

function PlayerForm({ player, tournamentId }: { player: OpenApi.Player; tournamentId: number }) {
  const form = useSavedForm({
    resolver: zodResolver(zPlayerBody),
    values: { active: player.active, name: player.name },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updatePlayerByIdApiTournamentsTournamentIdPlayersPlayerIdPutMutation(),
    meta: { successMessage: 'Player saved.' },
  });
  const remove = useMutation({
    ...deletePlayerApiTournamentsTournamentIdPlayersPlayerIdDeleteMutation(),
    meta: { successMessage: 'Player deleted.' },
  });
  const path = { player_id: player.id, tournament_id: tournamentId };

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <div className="grid items-end gap-x-4 md:grid-cols-2">
        <Field error={form.formState.errors.name?.message} label="Name">
          <input className="input w-full" required {...form.register('name')} />
        </Field>
        <CheckboxField className="mb-1" label="Active player" {...form.register('active')} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn btn-primary" disabled={update.isPending} type="submit">
          Save
        </button>
        <button
          className="btn btn-error btn-soft"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: 'Delete player',
                destructive: true,
                message: `Delete ${player.name}?`,
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          Delete
        </button>
      </div>
    </form>
  );
}

export function PlayersSection({ bundle }: { bundle: TournamentBundle }) {
  const tournamentId = bundle.tournament.id;
  const filter = useFilter(bundle.players, ['name']);

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Surface>
        <SurfaceHeading title="Roster intake" />
        <NewPlayerForm tournamentId={tournamentId} />
        <div className="border-t border-base-300 pt-4">
          <BulkPlayersForm tournamentId={tournamentId} />
        </div>
      </Surface>

      <Surface>
        <SurfaceHeading
          actions={
            <span className="text-sm text-base-content/70">{bundle.players.length} players</span>
          }
          title="Players"
        />
        {bundle.players.length === 0 ? (
          <p className="text-sm text-base-content/70">No players yet.</p>
        ) : (
          <FilterBox label="Search players" onChange={filter.setQuery} value={filter.query} />
        )}
        {filter.nothingMatches ? (
          <p className="text-sm text-base-content/70">No player matches “{filter.term}”.</p>
        ) : null}
        <div className="space-y-3">
          {bundle.players.map((player) => (
            <PlayerEditor
              hidden={!filter.isShown(player)}
              key={player.id}
              player={player}
              tournamentId={tournamentId}
            />
          ))}
        </div>
      </Surface>
    </div>
  );
}

// Checkboxes hold their values as strings.
const teamSchema = zTeamBody.extend({ player_ids: z.array(z.coerce.number().int()) });

/** Long enough that looking for a name by eye takes a while. */
const SEARCHABLE_PLAYER_COUNT = 12;

/** The teams each player is in, by player id. */
function groupTeamsByPlayer(teams: OpenApi.FullTeamWithPlayers[]) {
  return groupBy(
    teams.flatMap((team) => team.players.map((player) => ({ playerId: player.id, team }))),
    (membership) => membership.playerId,
  );
}

type TeamsByPlayer = ReturnType<typeof groupTeamsByPlayer>;

/** What the team forms need of the tournament: its players, and whose team they are in. */
type Roster = {
  players: OpenApi.Player[];
  /** Whether the tournament's settings let a player be in more than one team. */
  sharedPlayers: boolean;
  teamsByPlayer: TeamsByPlayer;
  tournamentId: number;
};

function PlayerChecklist({
  registration,
  roster: { players, sharedPlayers, teamsByPlayer },
  team,
}: {
  registration: UseFormRegisterReturn<'player_ids'>;
  roster: Roster;
  /** The team being edited. A new team has none. */
  team?: OpenApi.FullTeamWithPlayers;
}) {
  const filter = useFilter(players, ['name']);
  const members = new Set(team?.players.map((player) => player.id));
  const rows = players.map((player) => {
    const elsewhere = (teamsByPlayer.get(player.id) ?? [])
      .filter((membership) => membership.team.id !== team?.id)
      .map((membership) => membership.team.name);
    // Someone who is already in this team can always be taken out of it.
    const taken = elsewhere.length > 0 && !sharedPlayers && !members.has(player.id);
    return { elsewhere, player, taken };
  });
  // The players who can be picked come first: in a full tournament the others are most of the list.
  const ordered = rows.toSorted((left, right) => Number(left.taken) - Number(right.taken));

  return (
    <fieldset className="fieldset">
      <legend className="fieldset-legend">Players</legend>
      {players.length === 0 ? (
        <p className="text-sm text-base-content/70">Add players first to put them in teams.</p>
      ) : (
        <>
          {players.length >= SEARCHABLE_PLAYER_COUNT ? (
            <FilterBox
              className="sm:max-w-none"
              label="Search players"
              onChange={filter.setQuery}
              value={filter.query}
            />
          ) : null}
          {filter.nothingMatches ? (
            <p className="text-sm text-base-content/70">No player matches “{filter.term}”.</p>
          ) : null}
          <div className="grid max-h-60 gap-2 overflow-y-auto rounded-box border border-base-300 bg-base-100/40 p-3 sm:grid-cols-2">
            {ordered.map(({ elsewhere, player, taken }) => (
              <label
                className={cx(
                  'flex items-start gap-3 text-sm',
                  taken ? 'cursor-not-allowed text-base-content/60' : 'cursor-pointer',
                  !filter.isShown(player) && 'hidden',
                )}
                key={player.id}
              >
                <input
                  className="checkbox checkbox-primary checkbox-sm"
                  disabled={taken}
                  type="checkbox"
                  value={player.id}
                  {...registration}
                />
                <span>
                  {player.name}
                  {elsewhere.length > 0 ? (
                    <span className="block text-xs text-base-content/70">
                      in {elsewhere.join(', ')}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
          </div>
          {sharedPlayers ? null : (
            <p className="label whitespace-normal">
              A player can be in one team. The tournament's settings can allow more.
            </p>
          )}
        </>
      )}
    </fieldset>
  );
}

function NewTeamForm({ roster }: { roster: Roster }) {
  const form = useCreateForm({
    defaultValues: { active: true, name: '', player_ids: [] as string[] },
    resolver: zodResolver(teamSchema),
  });
  const create = useMutation({
    ...createTeamApiTournamentsTournamentIdTeamsPostMutation(),
    meta: { successMessage: 'Team created.' },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: roster.tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.name?.message} label="Team name">
          <input
            className="input w-full"
            placeholder="Arcade Wolves"
            required
            {...form.register('name')}
          />
        </Field>
        <CheckboxField className="mt-3" label="Team is active" {...form.register('active')} />
        <PlayerChecklist registration={form.register('player_ids')} roster={roster} />
        <button className="btn btn-primary mt-4" type="submit">
          Create team
        </button>
      </fieldset>
    </form>
  );
}

function BulkTeamsForm({ tournamentId }: { tournamentId: number }) {
  const form = useCreateForm({
    defaultValues: { active: true, names: '' },
    resolver: zodResolver(zTeamMultiBody),
  });
  const create = useMutation({
    ...createMultipleTeamsApiTournamentsTournamentIdTeamsMultiPostMutation(),
    meta: { successMessage: 'Teams created.' },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field error={form.formState.errors.names?.message} label="Team names">
          <textarea
            className="textarea min-h-28 w-full"
            placeholder={
              'One team per line, with its players after commas:\nRed Rockets, Anna, Ben'
            }
            {...form.register('names')}
          />
        </Field>
        <button className="btn btn-soft mt-4" type="submit">
          Create from list
        </button>
      </fieldset>
    </form>
  );
}

function TeamEditor({
  hidden,
  roster,
  team,
}: {
  hidden: boolean;
  roster: Roster;
  team: OpenApi.FullTeamWithPlayers;
}) {
  const logoUrl = teamLogoUrl(team);

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
            {team.players.map((player) => player.name).join(', ') || 'No players yet'}
          </span>
        </>
      }
    >
      <TeamForm roster={roster} team={team} />
    </Disclosure>
  );
}

function TeamForm({ roster, team }: { roster: Roster; team: OpenApi.FullTeamWithPlayers }) {
  const form = useSavedForm({
    resolver: zodResolver(teamSchema),
    values: {
      active: team.active,
      name: team.name,
      player_ids: team.players.map((player) => String(player.id)),
    },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateTeamByIdApiTournamentsTournamentIdTeamsTeamIdPutMutation(),
    meta: { successMessage: 'Team saved.' },
  });
  const uploadLogo = useMutation({
    ...updateTeamLogoApiTournamentsTournamentIdTeamsTeamIdLogoPostMutation(),
    meta: { successMessage: 'Logo updated.' },
  });
  const remove = useMutation({
    ...deleteTeamApiTournamentsTournamentIdTeamsTeamIdDeleteMutation(),
    meta: { successMessage: 'Team deleted.' },
  });
  const path = { team_id: team.id, tournament_id: roster.tournamentId };
  const logoUrl = teamLogoUrl(team);

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <Field error={form.formState.errors.name?.message} label="Team name">
        <input className="input w-full" required {...form.register('name')} />
      </Field>
      <CheckboxField className="mt-3" label="Active team" {...form.register('active')} />
      <LogoField
        isPending={uploadLogo.isPending}
        label="Team logo"
        logoUrl={logoUrl}
        onChange={(file) => uploadLogo.mutate({ body: { file }, path })}
      />
      <PlayerChecklist registration={form.register('player_ids')} roster={roster} team={team} />
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn btn-primary" disabled={update.isPending} type="submit">
          Save team
        </button>
        <button
          className="btn btn-error btn-soft"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: 'Delete team',
                destructive: true,
                message: `Delete ${team.name}?`,
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          Delete
        </button>
      </div>
    </form>
  );
}

export function TeamsSection({ bundle }: { bundle: TournamentBundle }) {
  const filter = useFilter(bundle.teams, ['name', 'players.*.name']);
  const roster = useMemo(
    () => ({
      players: bundle.players,
      sharedPlayers: bundle.tournament.players_can_be_in_multiple_teams,
      teamsByPlayer: groupTeamsByPlayer(bundle.teams),
      tournamentId: bundle.tournament.id,
    }),
    [bundle.players, bundle.teams, bundle.tournament],
  );

  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <SurfaceHeading title="Single team" />
          <NewTeamForm roster={roster} />
        </Surface>
        <Surface>
          <SurfaceHeading title="Batch team creation" />
          <BulkTeamsForm tournamentId={bundle.tournament.id} />
        </Surface>
      </div>

      <Surface>
        <SurfaceHeading
          actions={
            <span className="text-sm text-base-content/70">{bundle.teams.length} teams</span>
          }
          title="Teams"
        />
        {bundle.teams.length === 0 ? (
          <p className="text-sm text-base-content/70">No teams yet.</p>
        ) : (
          <FilterBox
            label="Search by team or player name"
            onChange={filter.setQuery}
            value={filter.query}
          />
        )}
        {filter.nothingMatches ? (
          <p className="text-sm text-base-content/70">No team or player matches “{filter.term}”.</p>
        ) : null}
        <div className="grid items-start gap-3 lg:grid-cols-2">
          {bundle.teams.map((team) => (
            <TeamEditor hidden={!filter.isShown(team)} key={team.id} roster={roster} team={team} />
          ))}
        </div>
      </Surface>
    </div>
  );
}
