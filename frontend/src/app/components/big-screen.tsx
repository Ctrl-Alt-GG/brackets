import { useIdle } from '@mantine/hooks';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router';

import { cx } from '../utils';

/** Kept with a big screen's history entry when a page opens it. */
type BigScreenState = { openedFromPage?: boolean } | null;

/** How long the exit stays visible after the last mouse, touch or keyboard input. */
const EXIT_VISIBLE_MS = 3_000;

/** Opens a big screen, which can then return to this page. */
export function BigScreenLink({ to }: { to: string }) {
  const { t } = useTranslation();

  return (
    <Link
      className="btn btn-ghost btn-sm"
      state={{ openedFromPage: true } satisfies BigScreenState}
      to={to}
    >
      {t('common.bigScreen')}
    </Link>
  );
}

/**
 * The tournament's name above a big screen, and the way back. The exit fades out while nobody uses
 * the screen, so it doesn't show on a projector or a stream, and comes back with the next input.
 */
export function BigScreenHeader({
  fallbackExitPath,
  title,
}: {
  /** Where the exit leads when the big screen wasn't opened from a page, as from a bookmark. */
  fallbackExitPath: string;
  title: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const state = useLocation().state as BigScreenState;
  const idle = useIdle(EXIT_VISIBLE_MS, { initialState: false });

  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="font-display text-4xl font-semibold tracking-tight md:text-5xl">{title}</h1>
      <button
        className={cx(
          'link link-hover text-sm text-base-content/70 transition-opacity duration-500',
          idle && 'opacity-0 focus-visible:opacity-100',
        )}
        onClick={() => {
          // The page that opened the big screen is the entry before it: going back returns there,
          // scrolled where it was, and leaves no extra entry in the history.
          if (state?.openedFromPage) void navigate(-1);
          else void navigate(fallbackExitPath);
        }}
        type="button"
      >
        {t('tournament.exitBigScreen')}
      </button>
    </header>
  );
}
