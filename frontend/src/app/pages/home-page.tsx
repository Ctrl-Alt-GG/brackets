import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  getClubsApiClubsGetOptions,
  getTournamentsApiTournamentsGetOptions,
} from '../../openapi/@tanstack/react-query.gen';
import { useServerNow } from '../clock';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { useSession } from '../hooks';
import { EmptyState, ErrorState, LoadingState, PageShell, Surface, SurfaceHeading } from '../ui';
import { getErrorMessage } from '../errors';
import { tournamentDateLabel } from '../format';
import { tournamentPhase } from '../tournament-rules';
import { publicTournamentPath } from '../urls';

function byStartTime(left: OpenApi.Tournament, right: OpenApi.Tournament) {
  return new Date(left.start_time).getTime() - new Date(right.start_time).getTime();
}

function TournamentCard({
  now,
  tournament,
}: {
  now: number;
  tournament: OpenApi.TournamentWithAccess;
}) {
  const { t } = useTranslation();
  const detailsPath = publicTournamentPath(tournament);
  const canManage = tournament.can_manage;

  return (
    <article className="card relative border border-base-300 bg-base-100/50 transition hover:border-primary/50 hover:bg-base-100/80">
      <div className="card-body gap-4">
        <div className="space-y-2">
          <TournamentStatusBadge now={now} tournament={tournament} />
          <h3 className="card-title font-display text-xl">{tournament.name}</h3>
          <p className="text-sm text-base-content/70">{tournamentDateLabel(tournament, t, now)}</p>
          {canManage ? (
            <p className="text-sm text-base-content/70">
              {t('home.timing', {
                duration: tournament.duration_minutes,
                margin: tournament.margin_minutes,
              })}
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
            {canManage ? t('common.manage') : t('common.details')}
          </Link>
          {canManage && tournament.dashboard_public ? (
            <Link className="btn btn-ghost btn-sm relative z-10" to={detailsPath}>
              {t('common.details')}
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function TournamentGroup({
  nested,
  now,
  title,
  tournaments,
}: {
  nested: boolean;
  now: number;
  title: string;
  tournaments: OpenApi.TournamentWithAccess[];
}) {
  if (tournaments.length === 0) return null;
  const Heading = nested ? 'h3' : 'h2';

  return (
    <section className="space-y-4">
      <Heading className="font-display text-xl font-semibold">{title}</Heading>
      <div className="grid gap-4 md:grid-cols-2">
        {tournaments.map((tournament) => (
          <TournamentCard key={tournament.id} now={now} tournament={tournament} />
        ))}
      </div>
    </section>
  );
}

/**
 * Running and upcoming tournaments in the order they start, then the most recent finished ones.
 * A tournament that is over belongs with the finished ones whether or not it was archived.
 */
function TournamentList({
  nested = false,
  now,
  tournaments,
}: {
  /** Under a heading of its own, which makes the groups subheadings. */
  nested?: boolean;
  now: number;
  tournaments: OpenApi.TournamentWithAccess[];
}) {
  const { t } = useTranslation();
  const active = tournaments
    .filter((tournament) => tournamentPhase(tournament, now) !== 'finished')
    .toSorted(byStartTime);
  const finished = tournaments
    .filter((tournament) => tournamentPhase(tournament, now) === 'finished')
    .toSorted(byStartTime)
    .toReversed();

  return (
    <div className="space-y-8">
      <TournamentGroup
        nested={nested}
        now={now}
        title={t('home.runningAndUpcoming')}
        tournaments={active}
      />
      <TournamentGroup
        nested={nested}
        now={now}
        title={t('home.finished')}
        tournaments={finished}
      />
    </div>
  );
}

// Only organizers create tournaments, so visitors never download the form.
const NewTournamentForm = lazy(() =>
  import('./new-tournament-form').then((module) => ({ default: module.NewTournamentForm })),
);

export function HomePage() {
  const { t } = useTranslation();
  const [session] = useSession();
  const canManage = Boolean(session);
  // The page stays open at the venue: a tournament that starts meanwhile moves on to running.
  const now = useServerNow();
  // Everyone sees the public tournaments: the running ones, and finished ones with the Details
  // page enabled. Organizers also see all tournaments of their events, and which they manage.
  const tournaments = useQuery(
    getTournamentsApiTournamentsGetOptions({ query: { filter_: 'ALL' } }),
  );
  const clubs = useQuery({ ...getClubsApiClubsGetOptions(), enabled: canManage });

  const all = tournaments.data?.data ?? [];
  const mine = all.filter((tournament) => tournament.can_manage);
  const others = all.filter((tournament) => !tournament.can_manage);

  const tournamentList = tournaments.isPending ? (
    <LoadingState title={t('home.loading')} />
  ) : tournaments.error ? (
    <ErrorState
      action={
        <button className="btn btn-sm" onClick={() => void tournaments.refetch()} type="button">
          {t('common.retry')}
        </button>
      }
      error={getErrorMessage(tournaments.error)}
      title={t('home.loadFailed')}
    />
  ) : all.length === 0 ? (
    <EmptyState
      text={canManage ? t('home.emptyOrganizer') : t('home.emptyVisitor')}
      title={t('home.emptyTitle')}
    />
  ) : canManage ? (
    <div className="space-y-10">
      <section className="space-y-6">
        <h2 className="font-display text-2xl font-semibold">{t('home.yours')}</h2>
        {mine.length > 0 ? (
          <TournamentList nested now={now} tournaments={mine} />
        ) : (
          <p className="text-sm text-base-content/70">{t('home.emptyOrganizer')}</p>
        )}
      </section>
      {others.length > 0 ? (
        <section className="space-y-6">
          <h2 className="font-display text-2xl font-semibold">{t('home.others')}</h2>
          <TournamentList nested now={now} tournaments={others} />
        </section>
      ) : null}
    </div>
  ) : (
    <TournamentList now={now} tournaments={all} />
  );

  return (
    <PageShell title={t('home.title')}>
      <title>{`${t('home.title')} · Ctrl-Alt-GG Bracket`}</title>
      {!canManage ? (
        tournamentList
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[1.6fr_1fr]">
          {tournamentList}
          <Surface>
            <SurfaceHeading title="New tournament" />
            {clubs.isPending ? (
              <LoadingState title="Loading events…" />
            ) : clubs.error ? (
              <ErrorState
                action={
                  <button className="btn btn-sm" onClick={() => void clubs.refetch()} type="button">
                    Retry loading events
                  </button>
                }
                error={getErrorMessage(clubs.error)}
                title="Unable to load events"
              />
            ) : clubs.data && clubs.data.data.length > 0 ? (
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
