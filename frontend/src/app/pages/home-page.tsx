import type { FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { fetchTournaments, unwrap } from '../api';
import { DateTimeField } from '../components/date-time-field';
import { runAction } from '../hooks';
import type { FlashMessage, Session } from '../types';
import {
  formatDateTime,
  getErrorMessage,
  normalizeDashboardEndpoint,
  toCheckbox,
  toNumber,
  toOptionalString,
  cx,
} from '../utils';
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageShell,
  Pill,
  Select,
  Surface,
  SurfaceHeading,
} from '../ui';
import { useState } from 'react';

export function HomePage({
  session,
  setFlash,
}: {
  session: Session;
  setFlash: (message: FlashMessage) => void;
}) {
  const [filter, setFilter] = useState<'ALL' | 'ARCHIVED' | 'OPEN'>(session ? 'ALL' : 'OPEN');
  const visibleFilter = session ? filter : 'OPEN';
  const queryClient = useQueryClient();
  const tournaments = useQuery({
    queryKey: ['tournaments', visibleFilter, session?.access_token],
    queryFn: () => fetchTournaments(visibleFilter, undefined, session?.access_token),
  });
  const clubs = useQuery({
    enabled: Boolean(session),
    queryKey: ['clubs', session?.access_token],
    queryFn: async () => {
      const response = await unwrap(OpenApi.getClubsApiClubsGet({ throwOnError: true }));
      return response.data;
    },
  });

  async function handleCreateTournament(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const startTime = String(formData.get('start_time') ?? '');

    if (!startTime) {
      setFlash({ text: 'Pick a start date and time.', tone: 'error' });
      return;
    }

    const success = await runAction(
      setFlash,
      async () => {
        await OpenApi.createTournamentApiTournamentsPost({
          body: {
            auto_assign_courts: toCheckbox(formData.get('auto_assign_courts')),
            club_id: toNumber(formData.get('club_id')),
            dashboard_endpoint: toOptionalString(formData.get('dashboard_endpoint')),
            dashboard_public: toCheckbox(formData.get('dashboard_public')),
            duration_minutes: toNumber(formData.get('duration_minutes'), 30),
            margin_minutes: toNumber(formData.get('margin_minutes'), 5),
            name: String(formData.get('name') ?? ''),
            players_can_be_in_multiple_teams: toCheckbox(
              formData.get('players_can_be_in_multiple_teams'),
            ),
            start_time: startTime,
          },
          throwOnError: true,
        });
      },
      'Tournament created successfully.',
      () => {
        void queryClient.invalidateQueries({ queryKey: ['tournaments'] });
        event.currentTarget.reset();
      },
    );

    if (success) void queryClient.invalidateQueries({ queryKey: ['clubs'] });
  }

  const tournamentList = (
    <Surface className="space-y-4">
      <SurfaceHeading
        actions={<Pill>{`${tournaments.data?.length ?? 0} total`}</Pill>}
        title="Tournaments"
      />
      <div className="grid gap-4 md:grid-cols-2">
        {tournaments.data?.map((tournament) => {
          const dashboardEndpoint = normalizeDashboardEndpoint(tournament.dashboard_endpoint);
          return (
            <article
              key={tournament.id}
              className="rounded-[1.5rem] border border-white/10 bg-black/20 p-5 transition hover:border-brand-300/40 hover:bg-black/30"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tone={tournament.status === 'OPEN' ? 'success' : 'default'}>
                      {tournament.status}
                    </Pill>
                    {tournament.dashboard_public ? (
                      <Pill tone="accent">public dashboard</Pill>
                    ) : null}
                  </div>
                  <h3 className="mt-4 font-display text-xl font-semibold text-white">
                    {tournament.name}
                  </h3>
                  <p className="mt-2 text-sm text-zinc-400">
                    Starts {formatDateTime(tournament.start_time)}. Duration{' '}
                    {tournament.duration_minutes} min with {tournament.margin_minutes} min margins.
                  </p>
                </div>
                <div className="text-right text-xs text-zinc-500">#{tournament.id}</div>
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                {session ? (
                  <Link
                    className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-500"
                    to={`/tournaments/${tournament.id}`}
                  >
                    Open workspace
                  </Link>
                ) : null}
                <Link
                  className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:bg-white/10"
                  to={`/tournaments/${tournament.id}/schedule`}
                >
                  Schedule
                </Link>
                <Link
                  className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:bg-white/10"
                  to={`/tournaments/${tournament.id}/results`}
                >
                  Results
                </Link>
                {dashboardEndpoint ? (
                  <Link
                    className="rounded-full border border-accent-400/40 bg-accent-500/10 px-4 py-2 text-sm font-semibold text-accent-200 transition hover:bg-accent-500/20"
                    to={`/tournaments/${dashboardEndpoint}/dashboard`}
                  >
                    Public dashboard
                  </Link>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </Surface>
  );

  if (!session) {
    return (
      <section className="space-y-6">
        {tournaments.isPending ? <LoadingState title="Loading tournaments…" /> : null}
        {tournaments.error ? (
          <ErrorState
            error={getErrorMessage(tournaments.error)}
            title="Unable to load tournaments"
          />
        ) : null}
        {!tournaments.isPending && !tournaments.error ? tournamentList : null}
      </section>
    );
  }

  return (
    <PageShell
      title="Tournament console"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {(['ALL', 'OPEN', 'ARCHIVED'] as const).map((value) => (
            <button
              className={cx(
                'rounded-full px-4 py-2 text-sm font-semibold transition',
                filter === value
                  ? 'bg-brand-600 text-white'
                  : 'bg-white/10 text-zinc-200 hover:bg-white/20',
              )}
              key={value}
              onClick={() => setFilter(value)}
              type="button"
            >
              {value.toLowerCase()}
            </button>
          ))}
        </div>
      }
    >
      {tournaments.isPending ? <LoadingState title="Loading tournaments…" /> : null}
      {tournaments.error ? (
        <ErrorState error={getErrorMessage(tournaments.error)} title="Unable to load tournaments" />
      ) : null}

      {!tournaments.isPending && !tournaments.error ? (
        <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
          {tournamentList}
          {session ? (
            <Surface className="space-y-4">
              <SurfaceHeading title="New tournament" />
              {clubs.data && clubs.data.length > 0 ? (
                <form className="space-y-4" onSubmit={handleCreateTournament}>
                  <FormField label="Tournament name">
                    <Input name="name" placeholder="Ctrl-Alt-GG Summer Cup" required />
                  </FormField>
                  <FormField label="Owning event">
                    <Select name="club_id" required>
                      {clubs.data.map((club) => (
                        <option key={club.id} value={club.id}>
                          {club.name}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField label="Start time">
                      <DateTimeField name="start_time" required />
                    </FormField>
                    <FormField label="Dashboard endpoint">
                      <Input name="dashboard_endpoint" placeholder="summer-cup-2026" />
                    </FormField>
                    <FormField label="Duration minutes">
                      <Input
                        defaultValue={30}
                        min={1}
                        name="duration_minutes"
                        required
                        type="number"
                      />
                    </FormField>
                    <FormField label="Margin minutes">
                      <Input
                        defaultValue={5}
                        min={0}
                        name="margin_minutes"
                        required
                        type="number"
                      />
                    </FormField>
                  </div>
                  <div className="grid gap-3 text-sm text-zinc-200">
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                      <input
                        className="h-4 w-4 accent-brand-500"
                        name="dashboard_public"
                        type="checkbox"
                      />
                      <span>Expose public dashboard routes</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                      <input
                        className="h-4 w-4 accent-brand-500"
                        name="players_can_be_in_multiple_teams"
                        type="checkbox"
                      />
                      <span>Allow players in multiple teams</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                      <input
                        className="h-4 w-4 accent-brand-500"
                        name="auto_assign_courts"
                        type="checkbox"
                      />
                      <span>Auto-assign courts during scheduling</span>
                    </label>
                  </div>
                  <Button type="submit">Create tournament</Button>
                </form>
              ) : (
                <EmptyState
                  text="You need at least one event before you can create a tournament."
                  title="Create an event first"
                  action={
                    <Link
                      className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
                      to="/events"
                    >
                      Open event manager
                    </Link>
                  }
                />
              )}
            </Surface>
          ) : null}
        </div>
      ) : null}
    </PageShell>
  );
}
