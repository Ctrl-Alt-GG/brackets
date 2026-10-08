import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router';

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
import { EmptyState, Field, PageShell, Surface } from '../ui';

const loginSchema = zBodyLoginForAccessTokenApiTokenPost.pick({ password: true, username: true });

export function LoginPage() {
  const navigate = useNavigate();
  const [, setSession] = useSession();
  const authFeatures = useQuery(getAuthFeaturesApiAuthFeaturesGetOptions());
  const form = useForm({
    defaultValues: { password: '', username: '' },
    resolver: zodResolver(loginSchema),
  });
  const login = useMutation({
    ...loginForAccessTokenApiTokenPostMutation(),
    meta: { successMessage: 'Logged in successfully.' },
    onSuccess: ({ name, user_id }) => {
      setSession({ name, user_id });
      navigate('/');
    },
  });

  return (
    <PageShell title="Organizer login">
      <Surface className="mx-auto w-full max-w-xl">
        <p className="text-sm text-base-content/80">
          Players don't need an account:{' '}
          <Link className="link font-semibold" to="/">
            open a tournament
          </Link>{' '}
          to see its schedule, teams and standings.
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
          <Field label="Email">
            <input
              autoComplete="username"
              className="input w-full"
              placeholder="captain@ctrl-alt-gg.hu"
              required
              type="email"
              {...form.register('username')}
            />
          </Field>
          <Field label="Password">
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
              {login.isPending ? 'Logging in…' : 'Log in'}
            </button>
            {authFeatures.data?.data.user_registration_enabled ? (
              <Link className="link text-sm" to="/create-account">
                Create account
              </Link>
            ) : null}
            <Link className="link text-sm" to="/password-reset">
              Password reset
            </Link>
          </div>
        </form>
      </Surface>
    </PageShell>
  );
}

// The server checks the strength, so the form only repeats the length rule for quick feedback.
const registerSchema = zUserToRegister.extend({ password: zUserPasswordToUpdate.shape.password });

export function RegisterPage() {
  const navigate = useNavigate();
  const [, setSession] = useSession();
  const authFeatures = useQuery(getAuthFeaturesApiAuthFeaturesGetOptions());
  const form = useForm({
    defaultValues: { email: '', name: '', password: '' },
    resolver: zodResolver(registerSchema),
  });
  const register = useMutation({
    ...registerUserApiUsersRegisterPostMutation(),
    meta: { successMessage: 'Account created successfully.' },
    onSuccess: ({ data: { name, user_id } }) => {
      setSession({ name, user_id });
      navigate('/');
    },
  });
  const { errors } = form.formState;

  if (authFeatures.data && !authFeatures.data.data.user_registration_enabled) {
    return (
      <PageShell title="Create an organizer account">
        <EmptyState
          action={
            <Link className="btn btn-ghost btn-sm" to="/login">
              Go to login
            </Link>
          }
          text="Account creation is currently disabled by the server configuration."
          title="Registration unavailable"
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Create an organizer account">
      <Surface className="mx-auto w-full max-w-2xl">
        <form onSubmit={form.handleSubmit((body) => register.mutate({ body }))}>
          <div className="grid gap-x-4 md:grid-cols-2">
            <Field error={errors.name?.message} label="Display name">
              <input
                className="input w-full"
                placeholder="Tournament director"
                required
                {...form.register('name')}
              />
            </Field>
            <Field error={errors.email?.message} label="Email">
              <input
                autoComplete="email"
                className="input w-full"
                placeholder="director@ctrl-alt-gg.hu"
                required
                type="email"
                {...form.register('email')}
              />
            </Field>
            <Field className="md:col-span-2" error={errors.password?.message} label="Password">
              <input
                autoComplete="new-password"
                className="input w-full"
                placeholder="Use at least twelve characters"
                required
                type="password"
                {...form.register('password')}
              />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button className="btn btn-primary" disabled={register.isPending} type="submit">
              {register.isPending ? 'Creating…' : 'Create account'}
            </button>
            <Link className="link text-sm" to="/login">
              I already have an account
            </Link>
          </div>
        </form>
      </Surface>
    </PageShell>
  );
}

export function PasswordResetStatusPage() {
  return (
    <PageShell title="Password reset">
      <Surface>
        <p className="text-sm text-base-content/80">Password reset is currently unavailable.</p>
      </Surface>
    </PageShell>
  );
}
