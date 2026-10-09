import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useForm, type UseFormRegisterReturn } from 'react-hook-form';
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
import type { TournamentBundle } from '../types';
import { CheckboxField, Field, Surface, SurfaceHeading } from '../ui';

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="badge badge-soft badge-success badge-sm">Active</span>
  ) : (
    <span className="badge badge-soft badge-sm">Inactive</span>
  );
}

function NewPlayerForm({ tournamentId }: { tournamentId: number }) {
  const form = useForm({
    defaultValues: { active: true, name: '' },
    resolver: zodResolver(zPlayerBody),
  });
  const create = useMutation({
    ...createSinglePlayerApiTournamentsTournamentIdPlayersPostMutation(),
    meta: { successMessage: 'Player added.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          { body, path: { tournament_id: tournamentId } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field error={form.formState.errors.name?.message} label="Player name">
        <input
          className="input w-full"
          placeholder="Mortal Kombat main"
          required
          {...form.register('name')}
        />
      </Field>
      <CheckboxField className="mt-3" label="Player is active" {...form.register('active')} />
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        Add player
      </button>
    </form>
  );
}

function BulkPlayersForm({ tournamentId }: { tournamentId: number }) {
  const form = useForm({
    defaultValues: { active: true, names: '' },
    resolver: zodResolver(zPlayerMultiBody),
  });
  const create = useMutation({
    ...createMultiplePlayersApiTournamentsTournamentIdPlayersMultiPostMutation(),
    meta: { successMessage: 'Players added.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          { body, path: { tournament_id: tournamentId } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field error={form.formState.errors.names?.message} label="Bulk import names">
        <textarea
          className="textarea min-h-28 w-full"
          placeholder="One player per line"
          {...form.register('names')}
        />
      </Field>
      <button className="btn btn-soft mt-4" disabled={create.isPending} type="submit">
        Bulk import
      </button>
    </form>
  );
}

function PlayerEditor({ player, tournamentId }: { player: OpenApi.Player; tournamentId: number }) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(zPlayerBody),
    values: { active: player.active, name: player.name },
  });
  const update = useMutation({
    ...updatePlayerByIdApiTournamentsTournamentIdPlayersPlayerIdPutMutation(),
    meta: { successMessage: 'Player saved.' },
  });
  const remove = useMutation({
    ...deletePlayerApiTournamentsTournamentIdPlayersPlayerIdDeleteMutation(),
    meta: { successMessage: 'Player deleted.' },
  });
  const path = { player_id: player.id, tournament_id: tournamentId };

  return (
    <details className="collapse collapse-arrow border border-base-300 bg-base-100/50">
      <summary className="collapse-title">
        <span className="flex flex-wrap items-center gap-2 font-semibold">
          {player.name}
          <ActiveBadge active={player.active} />
        </span>
        <span className="block text-sm text-base-content/70">
          {player.wins}W / {player.draws}D / {player.losses}L · ELO {player.elo_score}
        </span>
      </summary>
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
            onClick={() => {
              if (window.confirm(`Delete ${player.name}?`)) remove.mutate({ path });
            }}
            type="button"
          >
            Delete
          </button>
        </div>
      </form>
    </details>
  );
}

export function PlayersSection({ bundle }: { bundle: TournamentBundle }) {
  const tournamentId = bundle.tournament.id;

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
        ) : null}
        <div className="space-y-3">
          {bundle.players.map((player) => (
            <PlayerEditor key={player.id} player={player} tournamentId={tournamentId} />
          ))}
        </div>
      </Surface>
    </div>
  );
}

// Checkboxes hold their values as strings.
const teamSchema = zTeamBody.extend({ player_ids: z.array(z.coerce.number().int()) });

function PlayerChecklist({
  players,
  registration,
}: {
  players: OpenApi.Player[];
  registration: UseFormRegisterReturn<'player_ids'>;
}) {
  return (
    <fieldset className="fieldset">
      <legend className="fieldset-legend">Players</legend>
      {players.length === 0 ? (
        <p className="text-sm text-base-content/70">Add players first to put them in teams.</p>
      ) : (
        <div className="grid max-h-60 gap-2 overflow-y-auto rounded-box border border-base-300 bg-base-100/40 p-3 sm:grid-cols-2">
          {players.map((player) => (
            <label className="flex cursor-pointer items-center gap-3 text-sm" key={player.id}>
              <input
                className="checkbox checkbox-primary checkbox-sm"
                type="checkbox"
                value={player.id}
                {...registration}
              />
              {player.name}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function NewTeamForm({ bundle }: { bundle: TournamentBundle }) {
  const form = useForm({
    defaultValues: { active: true, name: '', player_ids: [] as string[] },
    resolver: zodResolver(teamSchema),
  });
  const create = useMutation({
    ...createTeamApiTournamentsTournamentIdTeamsPostMutation(),
    meta: { successMessage: 'Team created.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          { body, path: { tournament_id: bundle.tournament.id } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field error={form.formState.errors.name?.message} label="Team name">
        <input
          className="input w-full"
          placeholder="Arcade Wolves"
          required
          {...form.register('name')}
        />
      </Field>
      <CheckboxField className="mt-3" label="Team is active" {...form.register('active')} />
      <PlayerChecklist players={bundle.players} registration={form.register('player_ids')} />
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        Create team
      </button>
    </form>
  );
}

function BulkTeamsForm({ tournamentId }: { tournamentId: number }) {
  const form = useForm({
    defaultValues: { active: true, names: '' },
    resolver: zodResolver(zTeamMultiBody),
  });
  const create = useMutation({
    ...createMultipleTeamsApiTournamentsTournamentIdTeamsMultiPostMutation(),
    meta: { successMessage: 'Teams created.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          { body, path: { tournament_id: tournamentId } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field error={form.formState.errors.names?.message} label="Team names">
        <textarea
          className="textarea min-h-28 w-full"
          placeholder={'One team per line, with its players after commas:\nRed Rockets, Anna, Ben'}
          {...form.register('names')}
        />
      </Field>
      <button className="btn btn-soft mt-4" disabled={create.isPending} type="submit">
        Create from list
      </button>
    </form>
  );
}

function TeamEditor({
  players,
  team,
  tournamentId,
}: {
  players: OpenApi.Player[];
  team: OpenApi.FullTeamWithPlayers;
  tournamentId: number;
}) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(teamSchema),
    values: {
      active: team.active,
      name: team.name,
      player_ids: team.players.map((player) => String(player.id)),
    },
  });
  const update = useMutation({
    ...updateTeamByIdApiTournamentsTournamentIdTeamsTeamIdPutMutation(),
    meta: { successMessage: 'Team saved.' },
  });
  const uploadLogo = useMutation({
    ...updateTeamLogoApiTournamentsTournamentIdTeamsTeamIdLogoPostMutation(),
    meta: { successMessage: 'Logo uploaded.' },
  });
  const remove = useMutation({
    ...deleteTeamApiTournamentsTournamentIdTeamsTeamIdDeleteMutation(),
    meta: { successMessage: 'Team deleted.' },
  });
  const path = { team_id: team.id, tournament_id: tournamentId };

  return (
    <details className="collapse collapse-arrow border border-base-300 bg-base-100/50">
      <summary className="collapse-title">
        <span className="flex flex-wrap items-center gap-2 font-semibold">
          {team.name}
          <ActiveBadge active={team.active} />
        </span>
        <span className="block text-sm text-base-content/70">
          {team.players.map((player) => player.name).join(', ') || 'No players yet'}
        </span>
      </summary>
      <form
        className="collapse-content"
        onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
      >
        <Field error={form.formState.errors.name?.message} label="Team name">
          <input className="input w-full" required {...form.register('name')} />
        </Field>
        <CheckboxField className="mt-3" label="Active team" {...form.register('active')} />
        <Field label="Team logo">
          <input
            accept="image/*"
            className="file-input w-full"
            disabled={uploadLogo.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadLogo.mutate({ body: { file }, path });
            }}
            type="file"
          />
        </Field>
        <PlayerChecklist players={players} registration={form.register('player_ids')} />
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn btn-primary" disabled={update.isPending} type="submit">
            Save team
          </button>
          <button
            className="btn btn-error btn-soft"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${team.name}?`)) remove.mutate({ path });
            }}
            type="button"
          >
            Delete
          </button>
        </div>
      </form>
    </details>
  );
}

export function TeamsSection({ bundle }: { bundle: TournamentBundle }) {
  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <SurfaceHeading title="Single team" />
          <NewTeamForm bundle={bundle} />
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
        ) : null}
        <div className="grid items-start gap-3 lg:grid-cols-2">
          {bundle.teams.map((team) => (
            <TeamEditor
              key={team.id}
              players={bundle.players}
              team={team}
              tournamentId={bundle.tournament.id}
            />
          ))}
        </div>
      </Surface>
    </div>
  );
}
