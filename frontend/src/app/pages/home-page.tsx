import type { FormEvent } from 'react';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { fetchTournaments, unwrap } from '../api';
import { useResource, runAction } from '../hooks';
import type { FlashMessage, Session } from '../types';
import {
  formatDateTime,
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
  PageShell,
  Pill,
  Select,
  Surface,
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
  const tournaments = useResource(
    () => fetchTournaments(visibleFilter, undefined, session?.access_token),
    [visibleFilter, session?.access_token],
  );
  const clubs = useResource(
    async () => {
      const response = await unwrap(OpenApi.getClubsApiClubsGet({ throwOnError: true }));
      return response.data;
    },
    [session?.access_token],
    Boolean(session),
  );

  async function handleCreateTournament(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

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
            start_time: new Date(String(formData.get('start_time') ?? '')).toISOString(),
          },
          throwOnError: true,
        });
      },
      'Tournament created successfully.',
      () => {
        tournaments.refresh();
        event.currentTarget.reset();
      },
    );

    if (success) clubs.refresh();
  }

  const tournamentList = (
    <Surface className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
            Live inventory
          </p>
          <h2 className="mt-2 font-display text-2xl font-semibold text-white">Tournaments</h2>
        </div>
        <Pill>{`${tournaments.data?.length ?? 0} total`}</Pill>
      </div>
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
                <div className="text-right text-xs uppercase tracking-[0.3em] text-zinc-500">
                  #{tournament.id}
                </div>
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
        {tournaments.loading ? <div className="hidden" /> : null}
        {tournaments.error ? (
          <ErrorState error={tournaments.error} title="Unable to load tournaments" />
        ) : null}
        {!tournaments.loading && !tournaments.error ? tournamentList : null}
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
      {tournaments.loading ? <div className="hidden" /> : null}
      {tournaments.error ? (
        <ErrorState error={tournaments.error} title="Unable to load tournaments" />
      ) : null}

      {!tournaments.loading && !tournaments.error ? (
        <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
          {tournamentList}
          {session ? (
            <Surface className="space-y-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                  Create
                </p>
                <h2 className="mt-2 font-display text-2xl font-semibold text-white">
                  New tournament
                </h2>
              </div>
              {clubs.data && clubs.data.length > 0 ? (
                <form className="space-y-4" onSubmit={handleCreateTournament}>
                  <FormField label="Tournament name">
                    <Input name="name" placeholder="Ctrl-Alt-GG Summer Cup" required />
                  </FormField>
                  <FormField label="Owning club">
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
                      <Input name="start_time" required type="datetime-local" />
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
                  text="You need at least one club before you can create a tournament."
                  title="Create a club first"
                  action={
                    <Link
                      className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
                      to="/clubs"
                    >
                      Open club manager
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
