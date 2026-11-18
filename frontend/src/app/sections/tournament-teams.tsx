import { useState } from 'react';
import { matchSorter } from 'match-sorter';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { MatchCard } from '../components/match-card';
import { teamPath, useTournamentContext } from '../tournament-context';
import type { FlattenedMatch, TournamentBundle } from '../types';
import { pointsPhrase } from '../format';
import { involvesTeam, isBracket, isScored, stageItemName, stageItemStandings } from '../matches';
import { nextMatch } from '../tournament-rules';
import { teamLogoUrl } from '../urls';
import { sortTeamsByName } from '../utils';
import { EmptyState, SectionLabel, Surface, SurfaceHeading } from '../ui';
import { stageItemPath } from './tournament-overview';

/** A team's logo, when it has one. Decorative: the name is always next to it. */
function TeamLogo({ className, team }: { className: string; team: OpenApi.FullTeamWithPlayers }) {
  const url = teamLogoUrl(team);
  return url ? (
    <img alt="" className={`${className} shrink-0 rounded-field object-contain`} src={url} />
  ) : null;
}

function playerNames(team: OpenApi.FullTeamWithPlayers) {
  return team.players.map((player) => player.name).join(', ');
}

export function TeamDirectorySection({ teams }: { teams: OpenApi.FullTeamWithPlayers[] }) {
  const { t } = useTranslation();
  const { myTeamId, publicPath } = useTournamentContext();
  const [query, setQuery] = useState('');
  // Players often know their own name better than their team's, so both are searched.
  const shown = query.trim()
    ? matchSorter(teams, query.trim(), { keys: ['name', 'players.*.name'] })
    : sortTeamsByName(teams);

  return (
    <Surface>
      <SurfaceHeading
        actions={
          <span className="text-sm text-base-content/70">
            {t('common.teamCount', { count: teams.length })}
          </span>
        }
        title={t('tournament.teams')}
      />
      {teams.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('teams.noneYet')}</p>
      ) : (
        <input
          aria-label={t('teams.search')}
          className="input w-full sm:max-w-md"
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('teams.searchPlaceholder')}
          type="search"
          value={query}
        />
      )}
      {teams.length > 0 && shown.length === 0 ? (
        <p className="text-sm text-base-content/70">
          {t('teams.noMatch', { query: query.trim() })}
        </p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((team) => (
          <Link
            className="card border border-base-300 bg-base-100/50 p-4 transition hover:border-primary/50 hover:bg-base-100/80"
            key={team.id}
            to={teamPath(publicPath, team.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="flex items-center gap-2 font-semibold">
                <TeamLogo className="size-6" team={team} />
                {team.name}
              </h3>
              {team.id === myTeamId ? (
                <span className="badge badge-soft badge-accent badge-sm">
                  {t('common.yourTeam')}
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-base-content/70">
              {playerNames(team) || t('teams.noPlayers')}
            </p>
          </Link>
        ))}
      </div>
    </Surface>
  );
}

export function TeamDetailSection({
  bundle,
  matches,
  stageItemsById,
  teamId,
}: {
  bundle: TournamentBundle;
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamId: number | null;
}) {
  const { t } = useTranslation();
  const { myTeamId, publicPath, setMyTeamId } = useTournamentContext();
  const team = bundle.teams.find((candidate) => candidate.id === teamId);

  if (!team) {
    return (
      <EmptyState
        action={
          <Link className="btn btn-soft btn-sm" to={`${publicPath}/teams`}>
            {t('teams.allTeams')}
          </Link>
        }
        text={t('teams.notFoundText')}
        title={t('teams.notFoundTitle')}
      />
    );
  }

  const isMine = team.id === myTeamId;
  const teamMatches = matches.filter(({ match }) => involvesTeam(match, team.id));
  const next = nextMatch(teamMatches);
  const upcoming = teamMatches.filter(({ match }) => !isScored(match) && match !== next?.match);
  // The match being played comes first, even when an earlier one is still missing its result.
  const comingUp = next ? [next, ...upcoming] : upcoming;
  const played = teamMatches.filter(({ match }) => isScored(match)).toReversed();
  const placements = bundle.stages.flatMap((stage) =>
    stage.stage_items
      .filter((stageItem) => !isBracket(stageItem))
      .flatMap((stageItem) => {
        const entries = stageItemStandings(stageItem, bundle.standings);
        const index = entries.findIndex(({ input }) => input.team_id === team.id);
        if (index < 0) return [];
        return [{ entry: entries[index], position: index + 1, size: entries.length, stageItem }];
      }),
  );

  return (
    <div className="space-y-6">
      {/* An inline link ignores the vertical spacing of the list it sits in, so this is a flex row. */}
      <Link
        className="inline-flex items-center gap-1.5 text-sm font-medium text-base-content/70 transition hover:text-base-content"
        to={`${publicPath}/teams`}
      >
        <span aria-hidden="true">←</span>
        {t('teams.allTeams')}
      </Link>

      <Surface className={isMine ? 'border-accent/40' : undefined}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <h2 className="flex items-center gap-3 font-display text-3xl font-semibold">
              <TeamLogo className="size-12" team={team} />
              {team.name}
            </h2>
            {isMine ? (
              <span className="badge badge-soft badge-accent">{t('common.yourTeam')}</span>
            ) : null}
          </div>
          <button
            className={isMine ? 'btn btn-ghost btn-sm' : 'btn btn-soft btn-sm'}
            onClick={() => setMyTeamId(isMine ? null : team.id)}
            type="button"
          >
            {isMine ? t('teams.notMine') : t('teams.mine')}
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <section className="space-y-2">
            <SectionLabel>{t('teams.players')}</SectionLabel>
            {team.players.length === 0 ? (
              <p className="text-sm text-base-content/70">{t('teams.noPlayers')}</p>
            ) : (
              <ul className="grid gap-1 sm:grid-cols-2">
                {team.players.map((player) => (
                  <li key={player.id}>{player.name}</li>
                ))}
              </ul>
            )}
          </section>
          {placements.length > 0 ? (
            <section className="space-y-2">
              <SectionLabel>{t('teams.standing')}</SectionLabel>
              <ul className="space-y-1 text-sm">
                {placements.map(({ entry, position, size, stageItem }) => (
                  <li key={stageItem.id}>
                    <Link className="link font-medium" to={stageItemPath(publicPath, stageItem)}>
                      {stageItemName(stageItem, t)}
                    </Link>
                    : {t('teams.place', { position, size })} ·{' '}
                    {pointsPhrase(stageItem, entry.standing.points, t)}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </Surface>

      <Surface>
        <SurfaceHeading title={t('teams.matches')} />
        {teamMatches.length === 0 ? (
          <p className="text-sm text-base-content/70">
            {t('teams.noMatches', { team: team.name })}
          </p>
        ) : null}
        {comingUp.length > 0 ? (
          <section className="space-y-3">
            <SectionLabel>{t('teams.comingUp')}</SectionLabel>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {comingUp.map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          </section>
        ) : null}
        {played.length > 0 ? (
          <section className="space-y-3">
            <SectionLabel>{t('teams.results')}</SectionLabel>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {played.map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          </section>
        ) : null}
      </Surface>
    </div>
  );
}
