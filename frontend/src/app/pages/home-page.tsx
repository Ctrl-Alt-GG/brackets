import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  getClubsApiClubsGetOptions,
  getTournamentsApiTournamentsGetOptions,
} from '../../openapi/@tanstack/react-query.gen';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { useSession } from '../hooks';
import { EmptyState, ErrorState, LoadingState, PageShell, Surface, SurfaceHeading } from '../ui';
import { getErrorMessage, publicTournamentPath, tournamentDateLabel } from '../utils';

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
              sits above that layer to stay clickable on its own.
              While pressed, daisyUI nudges a button with `translate`, which would make the button
              the containing block of its own overlay: the overlay would shrink to the button on
              mousedown, the mouseup would land on the card instead, and the click would be lost.
              Keeping the button in place while it is pressed keeps the overlay over the card. */}
          <Link
            className="btn btn-primary btn-sm after:absolute after:inset-0 after:rounded-box active:translate-none"
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

// Only organizers create tournaments, so visitors never download the form.
const NewTournamentForm = lazy(() =>
  import('./new-tournament-form').then((module) => ({ default: module.NewTournamentForm })),
);

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
              <Suspense fallback={<LoadingState title="Loading…" />}>
                <NewTournamentForm clubs={clubs.data.data} />
              </Suspense>
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
