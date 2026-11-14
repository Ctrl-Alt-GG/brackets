import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { Link } from 'react-router';
import { z } from 'zod';

import * as OpenApi from '../../openapi';
import {
  getUserApiUsersMeGetOptions,
  putUserPasswordApiUsersUserIdPasswordPutMutation,
  updateUserDetailsApiUsersUserIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zUserPasswordToUpdate, zUserToUpdate } from '../../openapi/zod.gen';
import { useSession } from '../hooks';
import { useSavedForm } from '../saved-form';
import {
  CheckboxField,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageShell,
  Surface,
  SurfaceHeading,
} from '../ui';
import { formatDateTime, getErrorMessage } from '../utils';

function IdentityForm({ user }: { user: OpenApi.UserPublic }) {
  const [session, setSession] = useSession();
  const form = useSavedForm({
    resolver: zodResolver(zUserToUpdate),
    values: { current_password: '', email: user.email, name: user.name },
  });
  const email = useWatch({ control: form.control, name: 'email' });
  const emailChanged = email.trim().toLowerCase() !== user.email;
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateUserDetailsApiUsersUserIdPutMutation(),
    meta: { successMessage: 'Account saved.' },
    onSuccess: ({ data }) => {
      form.saveCallbacks.onSuccess();
      // The header shows the name the session remembers.
      if (session) setSession({ ...session, name: data.name });
      form.resetField('current_password', { defaultValue: '' });
    },
  });
  const { errors } = form.formState;

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        update.mutate({
          body: { ...body, current_password: emailChanged ? body.current_password : null },
          path: { user_id: user.id },
        }),
      )}
    >
      <Field error={errors.name?.message} label="Display name">
        <input className="input w-full" required {...form.register('name')} />
      </Field>
      <Field error={errors.email?.message} label="Email">
        <input className="input w-full" required type="email" {...form.register('email')} />
      </Field>
      {emailChanged ? (
        // The email is what the account signs in with, so changing it takes the password.
        <Field error={errors.current_password?.message} label="Current password">
          <input
            autoComplete="current-password"
            className="input w-full"
            required
            type="password"
            {...form.register('current_password')}
          />
        </Field>
      ) : null}
      <p className="mt-3 text-sm text-base-content/70">
        Account created {formatDateTime(user.created)}
      </p>
      <button className="btn btn-primary mt-4" disabled={update.isPending} type="submit">
        {update.isPending ? 'Saving…' : 'Save profile'}
      </button>
    </form>
  );
}

// A typo in a new password would lock the organizer out, and the site sends no email to reset it,
// so the new password is typed twice. The repetition is only checked here, never sent.
const passwordSchema = zUserPasswordToUpdate
  .extend({ repeated_password: z.string() })
  .refine((values) => values.password === values.repeated_password, {
    message: "The two new passwords aren't the same",
    path: ['repeated_password'],
  });

function PasswordForm({ userId }: { userId: number }) {
  const [showPasswords, setShowPasswords] = useState(false);
  const form = useForm({
    defaultValues: { current_password: '', password: '', repeated_password: '' },
    resolver: zodResolver(passwordSchema),
  });
  const update = useMutation({
    ...putUserPasswordApiUsersUserIdPasswordPutMutation(),
    meta: { successMessage: 'Password updated.' },
  });
  const { errors } = form.formState;
  const type = showPasswords ? 'text' : 'password';

  return (
    <form
      onSubmit={form.handleSubmit(({ current_password, password }) =>
        update.mutate(
          { body: { current_password, password }, path: { user_id: userId } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field error={errors.current_password?.message} label="Current password">
        <input
          autoComplete="current-password"
          className="input w-full"
          required
          type={type}
          {...form.register('current_password')}
        />
      </Field>
      <Field error={errors.password?.message} label="New password">
        <input
          autoComplete="new-password"
          className="input w-full"
          placeholder="At least twelve characters"
          required
          type={type}
          {...form.register('password')}
        />
      </Field>
      <Field error={errors.repeated_password?.message} label="Repeat the new password">
        <input
          autoComplete="new-password"
          className="input w-full"
          required
          type={type}
          {...form.register('repeated_password')}
        />
      </Field>
      <CheckboxField
        checked={showPasswords}
        className="mt-3"
        label="Show the passwords"
        onChange={(event) => setShowPasswords(event.target.checked)}
      />
      <button className="btn btn-primary mt-4" disabled={update.isPending} type="submit">
        {update.isPending ? 'Updating…' : 'Update password'}
      </button>
    </form>
  );
}

export function UserPage() {
  const [session] = useSession();
  const profile = useQuery({ ...getUserApiUsersMeGetOptions(), enabled: Boolean(session) });

  if (!session) {
    return (
      <PageShell title="Account">
        <EmptyState
          action={
            <Link className="btn btn-primary btn-sm" to="/login">
              Organizer login
            </Link>
          }
          text="Log in first to view or update your account."
          title="Organizers only"
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Account">
      {profile.isPending ? <LoadingState title="Loading account…" /> : null}
      {profile.error ? (
        <ErrorState
          action={
            <button className="btn btn-sm" onClick={() => void profile.refetch()} type="button">
              Retry
            </button>
          }
          error={getErrorMessage(profile.error)}
          title="Unable to load account"
        />
      ) : null}
      {profile.data ? (
        <div className="grid items-start gap-6 xl:grid-cols-2">
          <Surface>
            <SurfaceHeading title="Identity" />
            <IdentityForm user={profile.data.data} />
          </Surface>
          <Surface>
            <SurfaceHeading title="Password" />
            <PasswordForm userId={profile.data.data.id} />
          </Surface>
        </div>
      ) : null}
    </PageShell>
  );
}
