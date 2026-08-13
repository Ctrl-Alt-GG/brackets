import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Link, NavLink } from 'react-router';

import type { AuthFeatures, FlashMessage, Session } from './types';
import { cx } from './utils';

const BUTTON_BASE_CLASS =
  'inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60';
const BUTTON_GHOST_CLASS = 'border border-white/10 bg-transparent text-zinc-200 hover:bg-white/10';

export function PageShell({
  children,
  title,
  actions,
}: {
  actions?: ReactNode;
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-4 rounded-[1.75rem] border border-white/10 bg-white/5 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.28)] backdrop-blur md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-white md:text-4xl">
            {title}
          </h1>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function Surface({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        'rounded-[1.5rem] border border-white/10 bg-white/5 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.24)] backdrop-blur',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SurfaceHeading({ actions, title }: { actions?: ReactNode; title: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-display text-2xl font-semibold text-white">{title}</h2>
      {actions}
    </div>
  );
}

export function Pill({
  children,
  tone = 'default',
}: {
  children: ReactNode;
  tone?: 'accent' | 'default' | 'danger' | 'success';
}) {
  const toneClass =
    tone === 'accent'
      ? 'border-accent-400/40 bg-accent-500/15 text-accent-200'
      : tone === 'danger'
        ? 'border-red-400/40 bg-red-500/15 text-red-200'
        : tone === 'success'
          ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200'
          : 'border-white/10 bg-white/5 text-zinc-200';

  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em]',
        toneClass,
      )}
    >
      {children}
    </span>
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cx(
        'w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-brand-300 focus:bg-black/30',
        className,
      )}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cx(
        'min-h-28 w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-brand-300 focus:bg-black/30',
        className,
      )}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cx(
        'w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-brand-300 focus:bg-black/30',
        className,
      )}
    >
      {children}
    </select>
  );
}

export function Button({
  children,
  className,
  tone = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: 'ghost' | 'primary' | 'secondary' | 'danger';
}) {
  const toneClass =
    tone === 'secondary'
      ? 'bg-white/10 text-white hover:bg-white/20'
      : tone === 'ghost'
        ? BUTTON_GHOST_CLASS
        : tone === 'danger'
          ? 'bg-red-600 text-white hover:bg-red-500'
          : 'bg-brand-600 text-white hover:bg-brand-500';

  return (
    <button {...props} className={cx(BUTTON_BASE_CLASS, toneClass, className)}>
      {children}
    </button>
  );
}

export function FormField({
  children,
  error,
  label,
}: {
  children: ReactNode;
  error?: string | null;
  label: string;
}) {
  return (
    <label className="block space-y-2 text-sm text-zinc-300">
      <span className="font-medium text-zinc-100">{label}</span>
      {children}
      {error ? <span className="block text-xs font-medium text-brand-300">{error}</span> : null}
    </label>
  );
}

export function FlashBanner({ message }: { message: FlashMessage }) {
  if (!message) return null;

  return (
    <div
      className={cx(
        'rounded-2xl border px-4 py-3 text-sm font-medium',
        message.tone === 'success'
          ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-100'
          : 'border-red-400/40 bg-red-500/15 text-red-100',
      )}
    >
      {message.text}
    </div>
  );
}

export function LoadingState({ title }: { title: string }) {
  return (
    <Surface className="flex min-h-52 items-center justify-center text-zinc-300">
      <div className="space-y-3 text-center">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-brand-200/30 border-t-brand-300" />
        <p>{title}</p>
      </div>
    </Surface>
  );
}

export function ErrorState({
  action,
  error,
  title,
}: {
  action?: ReactNode;
  error: string;
  title: string;
}) {
  return (
    <Surface className="space-y-4 border-red-400/30 bg-red-500/10 text-red-100">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="text-sm text-red-100/90">{error}</p>
      {action}
    </Surface>
  );
}

export function EmptyState({
  action,
  text,
  title,
}: {
  action?: ReactNode;
  text: string;
  title: string;
}) {
  return (
    <Surface className="space-y-3 text-center">
      <h3 className="font-display text-2xl font-semibold text-white">{title}</h3>
      <p className="mx-auto max-w-xl text-sm text-zinc-300">{text}</p>
      {action}
    </Surface>
  );
}

export function TopNav({
  authFeatures,
  currentUserName,
  onLogout,
  session,
}: {
  authFeatures: AuthFeatures | null;
  currentUserName?: string | null;
  onLogout: () => void;
  session: Session;
}) {
  const showPrimaryNav = Boolean(session);

  return (
    <header className="border-b border-white/10 bg-black/20 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between md:px-8">
        <div className="space-y-1">
          <Link to="/" className="inline-flex items-center gap-3 text-white">
            <img
              alt=""
              aria-hidden="true"
              className="h-8 w-auto sm:h-9"
              src="/ctrl-alt-gg-mark.svg"
            />
            <span className="block font-display text-lg font-semibold text-zinc-200/90">
              Ctrl-Alt-GG Bracket
            </span>
          </Link>
        </div>

        {showPrimaryNav ? (
          <nav className="flex flex-wrap items-center gap-2 text-sm text-zinc-300">
            <NavLink
              className={({ isActive }) =>
                cx(
                  'rounded-full px-4 py-2 transition hover:bg-white/10 hover:text-white',
                  isActive && 'bg-white/10 text-white',
                )
              }
              end
              to="/"
            >
              Tournaments
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                cx(
                  'rounded-full px-4 py-2 transition hover:bg-white/10 hover:text-white',
                  isActive && 'bg-white/10 text-white',
                )
              }
              to="/events"
            >
              Events
            </NavLink>
          </nav>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          {session ? (
            <>
              <Link className={cx(BUTTON_BASE_CLASS, BUTTON_GHOST_CLASS)} to="/user">
                {currentUserName ?? 'Signed in'}
              </Link>
              <Button tone="ghost" onClick={onLogout}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/10"
              >
                Log in
              </Link>
              {authFeatures?.userRegistrationEnabled ? (
                <Link
                  to="/create-account"
                  className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-500"
                >
                  Create account
                </Link>
              ) : null}
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export class ErrorBoundary extends Component<
  { children: ReactNode; title?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[bracket] render error', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <ErrorState
        action={
          <Button onClick={() => window.location.reload()} tone="secondary">
            Reload the page
          </Button>
        }
        error={error.message || 'An unexpected error occurred.'}
        title={this.props.title ?? 'Something went wrong'}
      />
    );
  }
}
