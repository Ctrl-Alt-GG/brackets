import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Trans, useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

import {
  getAuthFeaturesApiAuthFeaturesGetOptions,
  loginForAccessTokenApiTokenPostMutation,
  registerUserApiUsersRegisterPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import {
  zBodyLoginForAccessTokenApiTokenPost,
  zUserPasswordToUpdate,
  zUserToRegister,
} from '../../openapi/zod.gen';
import { useSession } from '../hooks';
import { useOrganizerTranslation } from '../organizer-locales';
import { EmptyState, Field, PageShell, Surface } from '../ui';
import { safeNextPath } from '../urls';

const loginSchema = zBodyLoginForAccessTokenApiTokenPost.pick({ password: true, username: true });

/** In the visitor's language: players who follow the login link learn here that they need none. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [, setSession] = useSession();
  const authFeatures = useQuery(getAuthFeaturesApiAuthFeaturesGetOptions());
  const form = useForm({
    defaultValues: { password: '', username: '' },
    resolver: zodResolver(loginSchema),
  });
  const login = useMutation({
    ...loginForAccessTokenApiTokenPostMutation(),
    meta: { successMessage: t('login.loggedIn') },
    onSuccess: ({ name, user_id }) => {
      setSession({ name, started: Date.now(), user_id });
      // Back to where the organizer was, such as the tournament their session ended on.
      navigate(safeNextPath(searchParams.get('next')));
    },
  });

  return (
    <PageShell title={t('nav.organizerLogin')}>
      <Surface className="mx-auto w-full max-w-xl">
        <p className="text-sm text-base-content/80">
          <Trans
            components={{ tournaments: <Link className="link font-semibold" to="/" /> }}
            i18nKey="login.playersNeedNoAccount"
          />
        </p>
        <form
          onSubmit={form.handleSubmit((credentials) =>
            login.mutate({
              body: {
                ...credentials,
                client_id: null,
                client_secret: null,
                grant_type: 'password',
                scope: '',
              },
            }),
          )}
        >
          <Field label={t('login.email')}>
            <input
              autoComplete="username"
              className="input w-full"
              placeholder="captain@ctrl-alt-gg.hu"
              required
              type="email"
              {...form.register('username')}
            />
          </Field>
          <Field label={t('login.password')}>
            <input
              autoComplete="current-password"
              className="input w-full"
              required
              type="password"
              {...form.register('password')}
            />
          </Field>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button className="btn btn-primary" disabled={login.isPending} type="submit">
              {login.isPending ? t('login.loggingIn') : t('login.logIn')}
            </button>
            {authFeatures.data?.data.user_registration_enabled ? (
              <Link className="link text-sm" to="/create-account">
                {t('login.createAccount')}
              </Link>
            ) : null}
          </div>
          {/* The site sends no email: the administrator sets a new password on the server. */}
          <p className="mt-4 text-sm text-base-content/70">{t('login.forgotPassword')}</p>
        </form>
      </Surface>
    </PageShell>
  );
}

// The server checks the strength, so the form only repeats the length rule for quick feedback.
const registerSchema = zUserToRegister.extend({ password: zUserPasswordToUpdate.shape.password });

export function RegisterPage() {
  const { t } = useOrganizerTranslation();
  const navigate = useNavigate();
  const [, setSession] = useSession();
  const authFeatures = useQuery(getAuthFeaturesApiAuthFeaturesGetOptions());
  const form = useForm({
    defaultValues: { email: '', name: '', password: '' },
    resolver: zodResolver(registerSchema),
  });
  const register = useMutation({
    ...registerUserApiUsersRegisterPostMutation(),
    meta: { successMessage: t('register.created') },
    onSuccess: ({ data: { name, user_id } }) => {
      setSession({ name, started: Date.now(), user_id });
      navigate('/');
    },
  });
  const { errors } = form.formState;

  if (authFeatures.data && !authFeatures.data.data.user_registration_enabled) {
    return (
      <PageShell title={t('register.title')}>
        <EmptyState
          action={
            <Link className="btn btn-ghost btn-sm" to="/login">
              {t('register.goToLogin')}
            </Link>
          }
          text={t('register.unavailableText')}
          title={t('register.unavailableTitle')}
        />
      </PageShell>
    );
  }

  return (
    <PageShell title={t('register.title')}>
      <Surface className="mx-auto w-full max-w-2xl">
        <form onSubmit={form.handleSubmit((body) => register.mutate({ body }))}>
          <div className="grid gap-x-4 md:grid-cols-2">
            <Field error={errors.name?.message} label={t('common.displayName')}>
              <input
                className="input w-full"
                placeholder={t('register.displayNamePlaceholder')}
                required
                {...form.register('name')}
              />
            </Field>
            <Field error={errors.email?.message} label={t('common.email')}>
              <input
                autoComplete="email"
                className="input w-full"
                placeholder="director@ctrl-alt-gg.hu"
                required
                type="email"
                {...form.register('email')}
              />
            </Field>
            <Field
              className="md:col-span-2"
              error={errors.password?.message}
              label={t('account.password')}
            >
              <input
                autoComplete="new-password"
                className="input w-full"
                placeholder={t('register.passwordPlaceholder')}
                required
                type="password"
                {...form.register('password')}
              />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button className="btn btn-primary" disabled={register.isPending} type="submit">
              {register.isPending ? t('common.creating') : t('register.create')}
            </button>
            <Link className="link text-sm" to="/login">
              {t('register.haveAccount')}
            </Link>
          </div>
        </form>
      </Surface>
    </PageShell>
  );
}
