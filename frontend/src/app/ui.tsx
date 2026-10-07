import type { ComponentProps, ReactNode } from 'react';
import { Link, NavLink } from 'react-router';

import type { Session } from './types';
import { cx } from './utils';

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
      <header className="card border border-base-300 bg-base-200/60 backdrop-blur">
        <div className="card-body flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <h1 className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
            {title}
          </h1>
          {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
        </div>
      </header>
      {children}
    </section>
  );
}

export function Surface({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      className={cx('card border border-base-300 bg-base-200/60 backdrop-blur', className)}
      id={id}
    >
      <div className="card-body gap-4">{children}</div>
    </section>
  );
}

export function SurfaceHeading({ actions, title }: { actions?: ReactNode; title: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="card-title font-display text-2xl">{title}</h2>
      {actions}
    </div>
  );
}

/** A labelled form control with its validation message. */
export function Field({
  children,
  className,
  error,
  label,
}: {
  children: ReactNode;
  className?: string;
  error?: string;
  label: string;
}) {
  return (
    <label className={cx('fieldset', className)}>
      <span className="fieldset-legend">{label}</span>
      {children}
      {error ? <span className="label text-error">{error}</span> : null}
    </label>
  );
}

export function CheckboxField({
  className,
  description,
  label,
  ...props
}: Omit<ComponentProps<'input'>, 'type'> & { description?: string; label: string }) {
  return (
    <label
      className={cx(
        'flex cursor-pointer items-start gap-3 rounded-box border border-base-300 bg-base-100/40 px-4 py-3 text-sm',
        className,
      )}
    >
      <input {...props} className="checkbox checkbox-primary checkbox-sm mt-0.5" type="checkbox" />
      <span className="space-y-1">
        <span className="block">{label}</span>
        {description ? (
          <span className="block text-xs text-base-content/70">{description}</span>
        ) : null}
      </span>
    </label>
  );
}

export function LoadingState({ title }: { title: string }) {
  return (
    <Surface className="min-h-52 justify-center">
      <div className="flex flex-col items-center gap-3 text-base-content/80" role="status">
        <span className="loading loading-spinner loading-lg text-primary" />
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
    <div className="alert alert-error alert-soft flex-col items-start" role="alert">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-sm">{error}</p>
      {action}
    </div>
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
    <Surface className="text-center">
      <h3 className="font-display text-2xl font-semibold">{title}</h3>
      <p className="mx-auto max-w-xl text-sm text-base-content/80">{text}</p>
      {action ? <div className="flex justify-center">{action}</div> : null}
    </Surface>
  );
}

export function TopNav({
  currentUserName,
  onLogout,
  session,
}: {
  currentUserName?: string | null;
  onLogout: () => void;
  session: Session;
}) {
  return (
    <header className="border-b border-base-300 bg-base-100/40 backdrop-blur">
      <nav
        aria-label="Main"
        className="navbar mx-auto max-w-7xl flex-wrap gap-x-4 gap-y-3 px-5 md:px-8"
      >
        <Link className="flex items-center gap-3" to="/">
          <img
            alt=""
            aria-hidden="true"
            className="h-8 w-auto sm:h-9"
            src="/ctrl-alt-gg-mark.svg"
          />
          <span className="font-display text-base font-semibold text-base-content/90 sm:text-lg">
            Ctrl-Alt-GG Bracket
          </span>
        </Link>

        {session ? (
          <div className="order-last flex w-full gap-5 text-sm font-semibold md:order-none md:w-auto">
            {[
              ['/', 'Tournaments'],
              ['/events', 'Events'],
            ].map(([to, label]) => (
              <NavLink
                className={({ isActive }) =>
                  cx(
                    'border-b-2 py-1 transition',
                    isActive
                      ? 'border-primary text-base-content'
                      : 'border-transparent text-base-content/70 hover:text-base-content',
                  )
                }
                end
                key={to}
                to={to}
              >
                {label}
              </NavLink>
            ))}
          </div>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          {session ? (
            <>
              <Link className="btn btn-ghost btn-sm" to="/user">
                {currentUserName ?? 'Account'}
              </Link>
              <button className="btn btn-ghost btn-sm" onClick={onLogout} type="button">
                Log out
              </button>
            </>
          ) : (
            // Players never need an account, so visitors only get a quiet way in for organizers.
            <Link className="link link-hover text-sm font-semibold" to="/login">
              Organizer login
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}
