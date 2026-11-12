import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';

import { teamPath, useTournamentContext } from '../tournament-context';
import { cx } from '../utils';

/** A team's name, linking to its page with the players and matches once the team is known. */
export function TeamLink({
  children,
  className,
  teamId,
}: {
  children: ReactNode;
  className?: string;
  teamId: number | null;
}) {
  const { isBigScreen, publicPath } = useTournamentContext();
  const { pathname } = useLocation();
  const path = teamId == null ? null : teamPath(publicPath, teamId);
  // Nothing may look clickable unless clicking it does something: not an undecided slot, not a
  // name on a screen at the venue, and not a team's name on that team's own page.
  if (isBigScreen || path == null || pathname.replace(/\/$/, '') === path) {
    return <span className={className}>{children}</span>;
  }

  return (
    <Link className={cx('link decoration-base-content/25 underline-offset-4', className)} to={path}>
      {children}
    </Link>
  );
}
