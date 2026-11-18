import { type ReactNode } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router';

import * as OpenApi from '../../openapi';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { tournamentDateLabel } from '../format';
import { hasBracketView, isBracket } from '../matches';
import { tournamentLogoUrl } from '../urls';
import { cx } from '../utils';

export type Tab = { end?: boolean; label: string; to: string };

export function detailsTabs(
  publicPath: string,
  stages: OpenApi.StageWithStageItems[],
  t: TFunction,
): Tab[] {
  const stageItems = stages.flatMap((stage) => stage.stage_items);
  return [
    { end: true, label: t('tournament.overview'), to: publicPath },
    { label: t('tournament.schedule'), to: `${publicPath}/schedule` },
    ...(stageItems.some((stageItem) => !isBracket(stageItem))
      ? [{ label: t('tournament.standings'), to: `${publicPath}/standings` }]
      : []),
    ...(stageItems.some(hasBracketView)
      ? [{ label: t('tournament.bracket'), to: `${publicPath}/bracket` }]
      : []),
    { label: t('tournament.teams'), to: `${publicPath}/teams` },
  ];
}

export function workspaceTabs(tournamentId: number): Tab[] {
  const base = `/tournaments/${tournamentId}`;
  return [
    { end: true, label: 'Overview', to: base },
    { label: 'Players', to: `${base}/players` },
    { label: 'Teams', to: `${base}/teams` },
    { label: 'Stages', to: `${base}/stages` },
    { label: 'Schedule', to: `${base}/schedule` },
    { label: 'Rankings', to: `${base}/rankings` },
    { label: 'Settings', to: `${base}/settings` },
  ];
}

export function TournamentHeader({
  actions,
  matchCount,
  matchesPlayed,
  tabs,
  teamCount,
  tournament,
}: {
  actions: ReactNode;
  matchCount: number;
  matchesPlayed: number;
  tabs: Tab[];
  teamCount: number;
  tournament: OpenApi.Tournament;
}) {
  const { t } = useTranslation();
  const logoUrl = tournamentLogoUrl(tournament);

  return (
    <header className="card border border-base-300 bg-base-200/60 backdrop-blur">
      <div className="card-body gap-5 pb-0">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="space-y-3">
            <h1 className="flex items-center gap-3 font-display text-3xl font-semibold tracking-tight md:text-4xl">
              {/* Decorative: the name is right next to it. */}
              {logoUrl ? (
                <img
                  alt=""
                  className="size-12 shrink-0 rounded-field object-contain"
                  src={logoUrl}
                />
              ) : null}
              {tournament.name}
            </h1>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-base-content/70">
              <TournamentStatusBadge tournament={tournament} />
              <span>{tournamentDateLabel(tournament, t)}</span>
              {/* The line wraps on phones, where a separator would dangle at a line end. */}
              <span aria-hidden="true" className="hidden sm:inline">
                ·
              </span>
              <span>{t('common.teamCount', { count: teamCount })}</span>
              {matchCount > 0 ? (
                <>
                  <span aria-hidden="true" className="hidden sm:inline">
                    ·
                  </span>
                  <span>
                    {t('common.matchesPlayed', { played: matchesPlayed, total: matchCount })}
                  </span>
                </>
              ) : null}
            </p>
          </div>
          {actions}
        </div>
        <nav
          aria-label={t('tournament.pages')}
          className="tabs tabs-border flex-nowrap overflow-x-auto [scrollbar-width:none]"
        >
          {tabs.map((tab) => (
            <NavLink
              className={({ isActive }) => cx('tab shrink-0', isActive && 'tab-active')}
              end={tab.end}
              key={tab.to}
              to={tab.to}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
