import { Link, useNavigate } from 'react-router';
import type { FormEvent } from 'react';

import * as OpenApi from '../../openapi';
import { unwrap } from '../api';
import { runAction } from '../hooks';
import type { AuthFeatures, FlashMessage, Session } from '../types';
import { Button, EmptyState, FormField, Input, PageShell, Surface } from '../ui';

export function LoginPage({
  authFeatures,
  setFlash,
  setSession,
}: {
  authFeatures: AuthFeatures | null;
  setFlash: (message: FlashMessage) => void;
  setSession: (session: Session) => void;
}) {
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    const username = String(formData.get('username') ?? '');
    const password = String(formData.get('password') ?? '');

    const success = await runAction(
      setFlash,
      async () => {
        const response = await unwrap(
          OpenApi.loginForAccessTokenApiTokenPost({
            body: {
              client_id: null,
              client_secret: null,
              grant_type: 'password',
              password,
              scope: '',
              username,
            },
            throwOnError: true,
          }),
        );

        setSession(response);
      },
      'Logged in successfully.',
    );

    if (success) {
      navigate('/');
    }
  }

  return (
    <PageShell title="Log in">
      <Surface className="mx-auto max-w-xl space-y-6">
        <form className="space-y-4" onSubmit={handleSubmit}>
          <FormField label="Email">
            <Input name="username" placeholder="captain@ctrl-alt-gg.hu" required type="email" />
          </FormField>
          <FormField label="Password">
            <Input name="password" placeholder="••••••••" required type="password" />
          </FormField>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit">Log in</Button>
            {authFeatures?.userRegistrationEnabled ? (
              <Link
                className="text-sm text-zinc-300 underline decoration-brand-400/50 underline-offset-4 hover:text-white"
                to="/create-account"
              >
                Create account
              </Link>
            ) : null}
            <Link
              className="text-sm text-zinc-300 underline decoration-brand-400/50 underline-offset-4 hover:text-white"
              to="/password-reset"
            >
              Password reset
            </Link>
          </div>
        </form>
      </Surface>
    </PageShell>
  );
}

export function RegisterPage({
  authFeatures,
  setFlash,
  setSession,
}: {
  authFeatures: AuthFeatures | null;
  setFlash: (message: FlashMessage) => void;
  setSession: (session: Session) => void;
}) {
  const navigate = useNavigate();

  if (!authFeatures?.userRegistrationEnabled) {
    return (
      <PageShell title="Create account">
        <EmptyState
          action={
            <Link
              className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/10"
              to="/login"
            >
              Go to login
            </Link>
          }
          text="Account creation is currently disabled by the server configuration."
          title="Registration unavailable"
        />
      </PageShell>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    const success = await runAction(
      setFlash,
      async () => {
        const response = await unwrap(
          OpenApi.registerUserApiUsersRegisterPost({
            body: {
              email: String(formData.get('email') ?? ''),
              name: String(formData.get('name') ?? ''),
              password: String(formData.get('password') ?? ''),
            },
            throwOnError: true,
          }),
        );

        setSession(response.data);
      },
      'Account created successfully.',
    );

    if (success) navigate('/');
  }

  return (
    <PageShell title="Create account">
      <Surface className="mx-auto max-w-2xl space-y-6">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
          <FormField label="Display name">
            <Input name="name" placeholder="Tournament director" required />
          </FormField>
          <FormField label="Email">
            <Input name="email" placeholder="director@ctrl-alt-gg.hu" required type="email" />
          </FormField>
          <div className="md:col-span-2">
            <FormField label="Password">
              <Input
                minLength={12}
                name="password"
                placeholder="Use at least twelve characters"
                required
                type="password"
              />
            </FormField>
          </div>
          <div className="md:col-span-2 flex items-center gap-3">
            <Button type="submit">Create account</Button>
            <Link
              className="text-sm text-zinc-300 underline decoration-brand-400/50 underline-offset-4 hover:text-white"
              to="/login"
            >
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
      <Surface className="space-y-3">
        <p className="text-sm text-zinc-300">Password reset is currently unavailable.</p>
      </Surface>
    </PageShell>
  );
}
