import type { ReactNode } from 'react';
import { Link } from 'react-router';

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
  if (isBigScreen || teamId == null) return <span className={className}>{children}</span>;

  return (
    <Link
      className={cx('link decoration-base-content/25 underline-offset-4', className)}
      to={teamPath(publicPath, teamId)}
    >
      {children}
    </Link>
  );
}
