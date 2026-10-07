import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  createTournamentApiTournamentsPostMutation,
  getClubsApiClubsGetOptions,
  getTournamentsApiTournamentsGetOptions,
} from '../../openapi/@tanstack/react-query.gen';
import { zTournamentBody } from '../../openapi/zod.gen';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { useSession } from '../hooks';
import {
  CheckboxField,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageShell,
  Surface,
  SurfaceHeading,
} from '../ui';
import {
  DETAILS_PAGE_DESCRIPTION,
  getErrorMessage,
  publicTournamentPath,
  tournamentDateLabel,
  zLocalDateTime,
} from '../utils';

function TournamentCard({
  canManage,
  tournament,
}: {
  canManage: boolean;
  tournament: OpenApi.Tournament;
}) {
  const detailsPath = publicTournamentPath(tournament);

  return (
    <article className="card relative border border-base-300 bg-base-100/50 transition hover:border-primary/50 hover:bg-base-100/80">
      <div className="card-body gap-4">
        <div className="space-y-2">
          <TournamentStatusBadge tournament={tournament} />
          <h3 className="card-title font-display text-xl">{tournament.name}</h3>
          <p className="text-sm text-base-content/70">{tournamentDateLabel(tournament)}</p>
          {canManage ? (
            <p className="text-sm text-base-content/70">
              {tournament.duration_minutes}-minute matches, {tournament.margin_minutes}-minute
              breaks
            </p>
          ) : null}
        </div>
        <div className="card-actions mt-auto">
          {/* The first button stretches over the card, so the whole card opens it. The second one
              sits above that layer to stay clickable on its own. */}
          <Link
            className="btn btn-primary btn-sm after:absolute after:inset-0 after:rounded-box"
            to={canManage ? `/tournaments/${tournament.id}` : detailsPath}
          >
            {canManage ? 'Manage' : 'Details'}
          </Link>
          {canManage && tournament.dashboard_public ? (
            <Link className="btn btn-ghost btn-sm relative z-10" to={detailsPath}>
              Details
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function TournamentGroup({
  canManage,
  title,
  tournaments,
}: {
  canManage: boolean;
  title: string;
  tournaments: OpenApi.Tournament[];
}) {
  if (tournaments.length === 0) return null;

  return (
    <section className="space-y-4">
      <h2 className="font-display text-xl font-semibold">{title}</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {tournaments.map((tournament) => (
          <TournamentCard canManage={canManage} key={tournament.id} tournament={tournament} />
        ))}
      </div>
    </section>
  );
}

const newTournamentSchema = zTournamentBody.extend({ start_time: zLocalDateTime });

function NewTournamentForm({ clubs }: { clubs: OpenApi.Club[] }) {
  const form = useForm({
    defaultValues: {
      club_id: clubs[0]?.id,
      dashboard_endpoint: '',
      dashboard_public: true,
      duration_minutes: 30,
      margin_minutes: 5,
      name: '',
      players_can_be_in_multiple_teams: false,
      start_time: '',
    },
    resolver: zodResolver(newTournamentSchema),
  });
  const create = useMutation({
    ...createTournamentApiTournamentsPostMutation(),
    meta: { successMessage: 'Tournament created.' },
  });
  const { errors } = form.formState;

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate({ body }, { onSuccess: () => form.reset() }),
      )}
    >
      <Field error={errors.name?.message} label="Tournament name">
        <input
          className="input w-full"
          placeholder="Ctrl-Alt-GG Summer Cup"
          required
          {...form.register('name')}
        />
      </Field>
      <Field label="Event">
        <select
          className="select w-full"
          required
          {...form.register('club_id', { valueAsNumber: true })}
        >
          {clubs.map((club) => (
            <option key={club.id} value={club.id}>
              {club.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.start_time?.message} label="Start time">
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <Field label="Details link">
          <input
            className="input w-full"
            placeholder="summer-cup-2026"
            {...form.register('dashboard_endpoint')}
          />
        </Field>
        <Field error={errors.duration_minutes?.message} label="Match duration (minutes)">
          <input
            className="input w-full"
            min={1}
            required
            type="number"
            {...form.register('duration_minutes', { valueAsNumber: true })}
          />
        </Field>
        <Field error={errors.margin_minutes?.message} label="Break between rounds (minutes)">
          <input
            className="input w-full"
            min={0}
            required
            type="number"
            {...form.register('margin_minutes', { valueAsNumber: true })}
          />
        </Field>
      </div>
      <div className="mt-3 grid gap-3">
        <CheckboxField
          description={DETAILS_PAGE_DESCRIPTION}
          label="Enable the Details page"
          {...form.register('dashboard_public')}
        />
        <CheckboxField
          label="Allow players in multiple teams"
          {...form.register('players_can_be_in_multiple_teams')}
        />
      </div>
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        {create.isPending ? 'Creating…' : 'Create tournament'}
      </button>
    </form>
  );
}

export function HomePage() {
  const [session] = useSession();
  const canManage = Boolean(session);
  // Visitors see every public tournament: the running ones, and finished ones with the Details
  // page enabled. Organizers see all tournaments of their events.
  const tournaments = useQuery(
    getTournamentsApiTournamentsGetOptions({ query: { filter_: 'ALL' } }),
  );
  const clubs = useQuery({ ...getClubsApiClubsGetOptions(), enabled: canManage });

  const byStartTime = (left: OpenApi.Tournament, right: OpenApi.Tournament) =>
    new Date(left.start_time).getTime() - new Date(right.start_time).getTime();
  const all = tournaments.data?.data ?? [];
  // Running and upcoming tournaments in the order they start, then the most recent finished ones.
  const active = all.filter((tournament) => tournament.status === 'OPEN').toSorted(byStartTime);
  const finished = all
    .filter((tournament) => tournament.status !== 'OPEN')
    .toSorted(byStartTime)
    .toReversed();

  const tournamentList = tournaments.isPending ? (
    <LoadingState title="Loading tournaments…" />
  ) : tournaments.error ? (
    <ErrorState error={getErrorMessage(tournaments.error)} title="Unable to load tournaments" />
  ) : all.length === 0 ? (
    <EmptyState
      text={
        canManage
          ? 'Create your first tournament with the form on this page.'
          : 'Tournaments show up here as soon as the organizers publish them.'
      }
      title="No tournaments yet"
    />
  ) : (
    <div className="space-y-8">
      <TournamentGroup canManage={canManage} title="Running and upcoming" tournaments={active} />
      <TournamentGroup canManage={canManage} title="Finished" tournaments={finished} />
    </div>
  );

  return (
    <PageShell title="Tournaments">
      <title>Tournaments · Ctrl-Alt-GG Bracket</title>
      {!canManage ? (
        tournamentList
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[1.6fr_1fr]">
          {tournamentList}
          <Surface>
            <SurfaceHeading title="New tournament" />
            {clubs.data && clubs.data.data.length > 0 ? (
              <NewTournamentForm clubs={clubs.data.data} />
            ) : (
              <div className="space-y-3 text-sm text-base-content/80">
                <p>You need an event before you can create a tournament.</p>
                <Link className="link font-semibold" to="/events">
                  Create an event
                </Link>
              </div>
            )}
          </Surface>
        </div>
      )}
    </PageShell>
  );
}
