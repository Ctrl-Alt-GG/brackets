import {
  cloneElement,
  useId,
  useState,
  type ComponentProps,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, useLocation } from 'react-router';

import { LANGUAGES } from './locales';
import type { Session } from './types';
import { loginPath } from './urls';
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

/** A small heading for a group of content inside a Surface, set apart from the text below it. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-xs font-semibold tracking-wider text-base-content/60 uppercase">
      {children}
    </h3>
  );
}

type ControlProps = Pick<ComponentProps<'input'>, 'aria-describedby' | 'aria-invalid' | 'id'>;

/**
 * A labelled form control with its validation message, or a hint while there is none. The control
 * gets the id the label points to, and the message as its description, so screen readers read it
 * with the control. A field with more than one control, such as `LogoField`, has its own markup.
 */
export function Field({
  children,
  className,
  error,
  hint,
  label,
}: {
  children: ReactElement<ControlProps>;
  className?: string;
  error?: string;
  hint?: string;
  label: string;
}) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error || hint;

  return (
    <div className={cx('fieldset', className)}>
      <label className="fieldset-legend" htmlFor={id}>
        {label}
      </label>
      {cloneElement(children, {
        'aria-describedby': message ? messageId : undefined,
        'aria-invalid': error ? true : undefined,
        id,
      })}
      {message ? (
        <span className={cx('label', error ? 'text-error' : 'whitespace-normal')} id={messageId}>
          {message}
        </span>
      ) : null}
    </div>
  );
}

/**
 * The submit button of a form that edits something saved. It stands out while the form has changes
 * that aren't saved yet and stays quiet otherwise, so a page of editors shows what still needs
 * saving.
 */
export function SaveButton({
  children,
  className,
  dirty,
  disabled = false,
}: {
  children: ReactNode;
  className?: string;
  dirty: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      className={cx('btn', dirty ? 'btn-primary' : 'btn-soft', className)}
      disabled={disabled}
      type="submit"
    >
      {children}
    </button>
  );
}

/** A checkbox with its label, and a description that screen readers read after the label. */
export function CheckboxField({
  className,
  description,
  label,
  ...props
}: Omit<ComponentProps<'input'>, 'type'> & { description?: string; label: string }) {
  const id = useId();

  return (
    <label
      className={cx(
        'flex cursor-pointer items-start gap-3 rounded-box border border-base-300 bg-base-100/40 px-4 py-3 text-sm',
        className,
      )}
    >
      <input
        {...props}
        aria-describedby={description ? `${id}-description` : undefined}
        aria-labelledby={`${id}-label`}
        className="checkbox checkbox-primary checkbox-sm mt-0.5"
        type="checkbox"
      />
      <span className="space-y-1">
        <span className="block" id={`${id}-label`}>
          {label}
        </span>
        {description ? (
          <span className="block text-xs text-base-content/70" id={`${id}-description`}>
            {description}
          </span>
        ) : null}
      </span>
    </label>
  );
}

/**
 * A native `<details>` whose content is made the first time it opens, and kept from then on. A long
 * list of closed editors costs only their summaries, and an editor that was opened keeps what was
 * typed into it when it is closed again or a filter hides it.
 */
export function Disclosure({
  children,
  className,
  open = false,
  summary,
}: {
  /** Its content: `collapse-content` elements, which only show as direct children. */
  children: ReactNode;
  className?: string;
  /** Opens it, also when this becomes true later on. */
  open?: boolean;
  summary: ReactNode;
}) {
  const [opened, setOpened] = useState(open);

  return (
    <details
      className={className}
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
      open={open}
    >
      <summary className="collapse-title">{summary}</summary>
      {opened ? children : null}
    </details>
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

/** The pages where organizers log in or sign up, which don't link to themselves. */
const AUTH_PATHS: ReadonlySet<string> = new Set(['/login', '/create-account']);

export function TopNav({
  currentUserName,
  logoutPending = false,
  onLogout,
  session,
}: {
  currentUserName?: string | null;
  logoutPending?: boolean;
  onLogout: () => void;
  session: Session;
}) {
  const { pathname } = useLocation();
  const { t } = useTranslation();

  return (
    <header className="border-b border-base-300 bg-base-100/40 backdrop-blur">
      <nav
        aria-label={t('nav.main')}
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
              ['/', t('nav.tournaments')],
              ['/roster', t('nav.roster')],
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
          <LanguageSelect />
          {session ? (
            <>
              <Link className="btn btn-ghost btn-sm" to="/user">
                {currentUserName ?? t('nav.account')}
              </Link>
              <button
                className="btn btn-ghost btn-sm"
                disabled={logoutPending}
                onClick={onLogout}
                type="button"
              >
                {logoutPending ? t('nav.loggingOut') : t('nav.logOut')}
              </button>
            </>
          ) : AUTH_PATHS.has(pathname) ? null : (
            // Players never need an account, so visitors only get a quiet way in for organizers.
            <Link className="link link-hover text-sm font-semibold" to={loginPath(pathname)}>
              {t('nav.organizerLogin')}
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}

/** The language of the pages players open. This browser remembers the choice. */
function LanguageSelect() {
  const { i18n, t } = useTranslation();

  return (
    <select
      aria-label={t('nav.language')}
      className="select select-ghost select-sm w-auto"
      onChange={(event) => void i18n.changeLanguage(event.target.value)}
      value={i18n.resolvedLanguage}
    >
      {Object.entries(LANGUAGES).map(([language, name]) => (
        <option key={language} lang={language} value={language}>
          {name}
        </option>
      ))}
    </select>
  );
}
