import type { FormEvent } from 'react';

import * as OpenApi from '../../openapi';
import { runAction } from '../hooks';
import type { FlashMessage, TournamentBundle } from '../types';
import { toCheckbox } from '../utils';
import { Button, FormField, Input, Pill, Surface, SurfaceHeading, Textarea } from '../ui';

export function PlayersSection({
  bundle,
  onRefresh,
  setFlash,
}: {
  bundle: TournamentBundle;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Surface className="space-y-4">
        <SurfaceHeading title="Roster intake" />
        <form
          className="space-y-4"
          onSubmit={async (event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            await runAction(
              setFlash,
              async () => {
                await OpenApi.createSinglePlayerApiTournamentsTournamentIdPlayersPost({
                  body: {
                    active: toCheckbox(formData.get('active')),
                    name: String(formData.get('name') ?? ''),
                  },
                  path: { tournament_id: bundle.tournament.id },
                  throwOnError: true,
                });
              },
              'Player created successfully.',
              () => {
                event.currentTarget.reset();
                onRefresh();
              },
            );
          }}
        >
          <FormField label="Player name">
            <Input name="name" placeholder="Mortal Kombat main" required />
          </FormField>
          <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
            <input
              className="h-4 w-4 accent-brand-500"
              defaultChecked
              name="active"
              type="checkbox"
            />
            <span>Player is active</span>
          </label>
          <Button type="submit">Add player</Button>
        </form>
        <form
          className="space-y-4"
          onSubmit={async (event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            await runAction(
              setFlash,
              async () => {
                await OpenApi.createMultiplePlayersApiTournamentsTournamentIdPlayersMultiPost({
                  body: {
                    active: true,
                    names: String(formData.get('names') ?? ''),
                  },
                  path: { tournament_id: bundle.tournament.id },
                  throwOnError: true,
                });
              },
              'Bulk players created successfully.',
              () => {
                event.currentTarget.reset();
                onRefresh();
              },
            );
          }}
        >
          <FormField label="Bulk import names">
            <Textarea name="names" placeholder="One player per line" />
          </FormField>
          <Button tone="secondary" type="submit">
            Bulk import
          </Button>
        </form>
      </Surface>

      <Surface className="space-y-4">
        <SurfaceHeading
          actions={<Pill>{`${bundle.players.length} players`}</Pill>}
          title="Players"
        />
        <div className="space-y-4">
          {bundle.players.map((player) => (
            <details
              className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
              key={player.id}
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-white">{player.name}</h3>
                  <p className="text-sm text-zinc-400">
                    {player.wins}W / {player.draws}D / {player.losses}L · ELO {player.elo_score}
                  </p>
                </div>
                {player.active ? <Pill tone="success">active</Pill> : <Pill>inactive</Pill>}
              </summary>
              <form
                className="mt-4 grid gap-4 md:grid-cols-[1fr_auto_auto]"
                onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.updatePlayerByIdApiTournamentsTournamentIdPlayersPlayerIdPut({
                        body: {
                          active: toCheckbox(formData.get('active')),
                          name: String(formData.get('name') ?? ''),
                        },
                        path: { player_id: player.id, tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Player updated successfully.',
                    onRefresh,
                  );
                }}
              >
                <div className="grid gap-4 md:col-span-3 md:grid-cols-2">
                  <FormField label="Name">
                    <Input defaultValue={player.name} name="name" />
                  </FormField>
                  <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
                    <input
                      className="h-4 w-4 accent-brand-500"
                      defaultChecked={player.active}
                      name="active"
                      type="checkbox"
                    />
                    <span>Active player</span>
                  </label>
                </div>
                <Button type="submit">Save</Button>
                <Button
                  onClick={async () => {
                    if (!window.confirm(`Delete ${player.name}?`)) return;
                    await runAction(
                      setFlash,
                      async () => {
                        await OpenApi.deletePlayerApiTournamentsTournamentIdPlayersPlayerIdDelete({
                          path: { player_id: player.id, tournament_id: bundle.tournament.id },
                          throwOnError: true,
                        });
                      },
                      'Player deleted successfully.',
                      onRefresh,
                    );
                  }}
                  tone="danger"
                  type="button"
                >
                  Delete
                </Button>
              </form>
            </details>
          ))}
        </div>
      </Surface>
    </div>
  );
}

export function TeamsSection({
  bundle,
  onRefresh,
  setFlash,
}: {
  bundle: TournamentBundle;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface className="space-y-4">
          <SurfaceHeading title="Single team" />
          <form
            className="space-y-4"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              const playerIds = bundle.players
                .map((player) => ({ checked: formData.get(`player_${player.id}`), id: player.id }))
                .filter((entry) => entry.checked === 'on')
                .map((entry) => entry.id);

              await runAction(
                setFlash,
                async () => {
                  await OpenApi.createTeamApiTournamentsTournamentIdTeamsPost({
                    body: {
                      active: toCheckbox(formData.get('active')),
                      name: String(formData.get('name') ?? ''),
                      player_ids: playerIds,
                    },
                    path: { tournament_id: bundle.tournament.id },
                    throwOnError: true,
                  });
                },
                'Team created successfully.',
                () => {
                  event.currentTarget.reset();
                  onRefresh();
                },
              );
            }}
          >
            <FormField label="Team name">
              <Input name="name" placeholder="Arcade Wolves" required />
            </FormField>
            <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
              <input
                className="h-4 w-4 accent-brand-500"
                defaultChecked
                name="active"
                type="checkbox"
              />
              <span>Team is active</span>
            </label>
            <div className="grid max-h-60 gap-2 overflow-y-auto rounded-[1.25rem] border border-white/10 bg-black/20 p-3 text-sm text-zinc-200">
              {bundle.players.map((player) => (
                <label className="flex items-center gap-3" key={player.id}>
                  <input
                    className="h-4 w-4 accent-brand-500"
                    name={`player_${player.id}`}
                    type="checkbox"
                  />
                  <span>{player.name}</span>
                </label>
              ))}
            </div>
            <Button type="submit">Create team</Button>
          </form>
        </Surface>

        <Surface className="space-y-4">
          <SurfaceHeading title="Batch team creation" />
          <form
            className="space-y-4"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              await runAction(
                setFlash,
                async () => {
                  await OpenApi.createMultipleTeamsApiTournamentsTournamentIdTeamsMultiPost({
                    body: {
                      active: true,
                      names: String(formData.get('names') ?? ''),
                    },
                    path: { tournament_id: bundle.tournament.id },
                    throwOnError: true,
                  });
                },
                'Bulk teams created successfully.',
                () => {
                  event.currentTarget.reset();
                  onRefresh();
                },
              );
            }}
          >
            <FormField label="Team names">
              <Textarea name="names" placeholder="One team per line" />
            </FormField>
            <Button tone="secondary" type="submit">
              Create from list
            </Button>
          </form>
        </Surface>
      </div>

      <Surface className="space-y-4">
        <SurfaceHeading actions={<Pill>{`${bundle.teams.length} teams`}</Pill>} title="Teams" />
        <div className="grid gap-4 lg:grid-cols-2">
          {bundle.teams.map((team) => (
            <details
              className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
              key={team.id}
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-white">{team.name}</h3>
                  <p className="text-sm text-zinc-400">
                    {team.players.map((player) => player.name).join(', ') || 'No players yet'}
                  </p>
                </div>
                {team.active ? <Pill tone="success">active</Pill> : <Pill>inactive</Pill>}
              </summary>
              <form
                className="mt-4 space-y-4"
                onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  const playerIds = bundle.players
                    .map((player) => ({
                      checked: formData.get(`player_${team.id}_${player.id}`),
                      id: player.id,
                    }))
                    .filter((entry) => entry.checked === 'on')
                    .map((entry) => entry.id);

                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.updateTeamByIdApiTournamentsTournamentIdTeamsTeamIdPut({
                        body: {
                          active: toCheckbox(formData.get('active')),
                          name: String(formData.get('name') ?? ''),
                          player_ids: playerIds,
                        },
                        path: { team_id: team.id, tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });

                      const file = formData.get('logo');
                      if (file instanceof File && file.size > 0) {
                        await OpenApi.updateTeamLogoApiTournamentsTournamentIdTeamsTeamIdLogoPost({
                          body: { file },
                          path: { team_id: team.id, tournament_id: bundle.tournament.id },
                          throwOnError: true,
                        });
                      }
                    },
                    'Team updated successfully.',
                    onRefresh,
                  );
                }}
              >
                <FormField label="Team name">
                  <Input defaultValue={team.name} name="name" />
                </FormField>
                <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
                  <input
                    className="h-4 w-4 accent-brand-500"
                    defaultChecked={team.active}
                    name="active"
                    type="checkbox"
                  />
                  <span>Active team</span>
                </label>
                <FormField label="Team logo">
                  <Input accept="image/*" name="logo" type="file" />
                </FormField>
                <div className="grid max-h-56 gap-2 overflow-y-auto rounded-[1.25rem] border border-white/10 bg-black/20 p-3 text-sm text-zinc-200">
                  {bundle.players.map((player) => (
                    <label className="flex items-center gap-3" key={player.id}>
                      <input
                        className="h-4 w-4 accent-brand-500"
                        defaultChecked={team.players.some((member) => member.id === player.id)}
                        name={`player_${team.id}_${player.id}`}
                        type="checkbox"
                      />
                      <span>{player.name}</span>
                    </label>
                  ))}
                </div>
                <div className="flex flex-wrap gap-3">
                  <Button type="submit">Save team</Button>
                  <Button
                    onClick={async () => {
                      if (!window.confirm(`Delete ${team.name}?`)) return;
                      await runAction(
                        setFlash,
                        async () => {
                          await OpenApi.deleteTeamApiTournamentsTournamentIdTeamsTeamIdDelete({
                            path: { team_id: team.id, tournament_id: bundle.tournament.id },
                            throwOnError: true,
                          });
                        },
                        'Team deleted successfully.',
                        onRefresh,
                      );
                    }}
                    tone="danger"
                    type="button"
                  >
                    Delete
                  </Button>
                </div>
              </form>
            </details>
          ))}
        </div>
      </Surface>
    </div>
  );
}
