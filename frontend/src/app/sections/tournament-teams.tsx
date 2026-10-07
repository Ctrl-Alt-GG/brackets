import { useState } from 'react';
import { matchSorter } from 'match-sorter';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { MatchCard } from '../components/match-card';
import { teamPath, useTournamentContext } from '../tournament-context';
import type { FlattenedMatch, TournamentBundle } from '../types';
import {
  involvesTeam,
  isBracket,
  isScored,
  nextMatch,
  pointsPhrase,
  sortTeamsByName,
  stageItemStandings,
} from '../utils';
import { EmptyState, Surface, SurfaceHeading } from '../ui';
import { stageItemPath } from './tournament-overview';

function playerNames(team: OpenApi.FullTeamWithPlayers) {
  return team.players.map((player) => player.name).join(', ');
}

export function TeamDirectorySection({ teams }: { teams: OpenApi.FullTeamWithPlayers[] }) {
  const { myTeamId, publicPath } = useTournamentContext();
  const [query, setQuery] = useState('');
  // Players often know their own name better than their team's, so both are searched.
  const shown = query.trim()
    ? matchSorter(teams, query.trim(), { keys: ['name', 'players.*.name'] })
    : sortTeamsByName(teams);

  return (
    <Surface>
      <SurfaceHeading
        actions={<span className="text-sm text-base-content/70">{teams.length} teams</span>}
        title="Teams"
      />
      {teams.length === 0 ? (
        <p className="text-sm text-base-content/70">No teams have signed up yet.</p>
      ) : (
        <input
          aria-label="Search teams and players"
          className="input w-full sm:max-w-md"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by team or player name"
          type="search"
          value={query}
        />
      )}
      {teams.length > 0 && shown.length === 0 ? (
        <p className="text-sm text-base-content/70">No team or player matches “{query.trim()}”.</p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((team) => (
          <Link
            className="card border border-base-300 bg-base-100/50 p-4 transition hover:border-primary/50 hover:bg-base-100/80"
            key={team.id}
            to={teamPath(publicPath, team.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold">{team.name}</h3>
              {team.id === myTeamId ? (
                <span className="badge badge-soft badge-accent badge-sm">Your team</span>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-base-content/70">
              {playerNames(team) || 'No players listed'}
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
  const { myTeamId, publicPath, setMyTeamId } = useTournamentContext();
  const team = bundle.teams.find((candidate) => candidate.id === teamId);

  if (!team) {
    return (
      <EmptyState
        action={
          <Link className="btn btn-soft btn-sm" to={`${publicPath}/teams`}>
            See all teams
          </Link>
        }
        text="This team isn't part of the tournament, or it has been removed."
        title="Team not found"
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
      <Link className="link text-sm" to={`${publicPath}/teams`}>
        ← All teams
      </Link>

      <Surface className={isMine ? 'border-accent/40' : undefined}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <h2 className="font-display text-3xl font-semibold">{team.name}</h2>
            {isMine ? <span className="badge badge-soft badge-accent">Your team</span> : null}
          </div>
          <button
            className={isMine ? 'btn btn-ghost btn-sm' : 'btn btn-soft btn-sm'}
            onClick={() => setMyTeamId(isMine ? null : team.id)}
            type="button"
          >
            {isMine ? 'This is not my team' : 'This is my team'}
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <section className="space-y-2">
            <h3 className="text-sm font-medium text-base-content/80">Players</h3>
            {team.players.length === 0 ? (
              <p className="text-sm text-base-content/70">No players listed.</p>
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
              <h3 className="text-sm font-medium text-base-content/80">Standing</h3>
              <ul className="space-y-1 text-sm">
                {placements.map(({ entry, position, size, stageItem }) => (
                  <li key={stageItem.id}>
                    <Link className="link font-medium" to={stageItemPath(publicPath, stageItem)}>
                      {stageItem.name || stageItem.type_name}
                    </Link>
                    : #{position} of {size} · {pointsPhrase(stageItem, entry.standing.points)}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </Surface>

      <Surface>
        <SurfaceHeading title="Matches" />
        {teamMatches.length === 0 ? (
          <p className="text-sm text-base-content/70">{team.name} has no matches yet.</p>
        ) : null}
        {comingUp.length > 0 ? (
          <section className="space-y-3">
            <h3 className="text-sm font-medium text-base-content/80">Coming up</h3>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {comingUp.map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          </section>
        ) : null}
        {played.length > 0 ? (
          <section className="space-y-3">
            <h3 className="text-sm font-medium text-base-content/80">Results</h3>
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
