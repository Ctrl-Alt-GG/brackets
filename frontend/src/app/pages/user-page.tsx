import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useWatch } from 'react-hook-form';
import { Link } from 'react-router';
import { z } from 'zod';

import * as OpenApi from '../../openapi';
import {
  getUserApiUsersMeGetOptions,
  getUserApiUsersMeGetQueryKey,
  putUserPasswordApiUsersUserIdPasswordPutMutation,
  updateUserDetailsApiUsersUserIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zUserPasswordToUpdate, zUserToUpdate } from '../../openapi/zod.gen';
import { useCreateForm } from '../create-form';
import { useSession } from '../hooks';
import { organizerT, useOrganizerTranslation } from '../organizer-locales';
import { queryClient } from '../query-client';
import { useSavedForm } from '../saved-form';
import {
  CheckboxField,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageShell,
  SaveButton,
  Surface,
  SurfaceHeading,
} from '../ui';
import { getErrorMessage } from '../errors';
import { formatDateTime } from '../format';

function IdentityForm({ user }: { user: OpenApi.UserPublic }) {
  const { t } = useOrganizerTranslation();
  const form = useSavedForm({
    resolver: zodResolver(zUserToUpdate),
    values: { current_password: '', email: user.email, name: user.name },
  });
  const email = useWatch({ control: form.control, name: 'email' });
  const emailChanged = email.trim().toLowerCase() !== user.email;
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateUserDetailsApiUsersUserIdPutMutation(),
    // The answer is the saved account, which is all that changed. The header follows its name.
    meta: { invalidates: [], successMessage: t('account.saved') },
    onSuccess: (response) => {
      queryClient.setQueryData(getUserApiUsersMeGetQueryKey(), response);
      form.saveCallbacks.onSuccess();
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
      <Field error={errors.name?.message} label={t('common.displayName')}>
        <input className="input w-full" required {...form.register('name')} />
      </Field>
      <Field error={errors.email?.message} label={t('common.email')}>
        <input className="input w-full" required type="email" {...form.register('email')} />
      </Field>
      {emailChanged ? (
        // The email is what the account signs in with, so changing it takes the password.
        <Field error={errors.current_password?.message} label={t('common.currentPassword')}>
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
        {t('account.created', { date: formatDateTime(user.created) })}
      </p>
      <SaveButton className="mt-4" dirty={form.formState.isDirty} disabled={update.isPending}>
        {update.isPending ? t('common.saving') : t('account.saveProfile')}
      </SaveButton>
    </form>
  );
}

// A typo in a new password would lock the organizer out, and the site sends no email to reset it,
// so the new password is typed twice. The repetition is only checked here, never sent.
const passwordSchema = zUserPasswordToUpdate
  .extend({ repeated_password: z.string() })
  .refine((values) => values.password === values.repeated_password, {
    error: () => organizerT('validation.passwordsDiffer'),
    path: ['repeated_password'],
  });

function PasswordForm({ userId }: { userId: number }) {
  const { t } = useOrganizerTranslation();
  const [showPasswords, setShowPasswords] = useState(false);
  const form = useCreateForm({
    defaultValues: { current_password: '', password: '', repeated_password: '' },
    resolver: zodResolver(passwordSchema),
  });
  const update = useMutation({
    ...putUserPasswordApiUsersUserIdPasswordPutMutation(),
    meta: { invalidates: [], successMessage: t('account.passwordUpdated') },
  });
  const { errors } = form.formState;
  const type = showPasswords ? 'text' : 'password';

  return (
    <form
      onSubmit={form.submitWith(({ current_password, password }) =>
        update.mutateAsync({ body: { current_password, password }, path: { user_id: userId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field error={errors.current_password?.message} label={t('common.currentPassword')}>
          <input
            autoComplete="current-password"
            className="input w-full"
            required
            type={type}
            {...form.register('current_password')}
          />
        </Field>
        <Field error={errors.password?.message} label={t('account.newPassword')}>
          <input
            autoComplete="new-password"
            className="input w-full"
            placeholder={t('account.newPasswordPlaceholder')}
            required
            type={type}
            {...form.register('password')}
          />
        </Field>
        <Field error={errors.repeated_password?.message} label={t('account.repeatPassword')}>
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
          label={t('account.showPasswords')}
          onChange={(event) => setShowPasswords(event.target.checked)}
        />
        <button className="btn btn-primary mt-4" type="submit">
          {update.isPending ? t('account.updating') : t('account.updatePassword')}
        </button>
      </fieldset>
    </form>
  );
}

export function UserPage() {
  const { t } = useOrganizerTranslation();
  const [session] = useSession();
  const profile = useQuery({ ...getUserApiUsersMeGetOptions(), enabled: Boolean(session) });

  if (!session) {
    return (
      <PageShell title={t('account.title')}>
        <EmptyState
          action={
            <Link className="btn btn-primary btn-sm" to="/login">
              {t('account.logIn')}
            </Link>
          }
          text={t('account.signedOutText')}
          title={t('account.signedOutTitle')}
        />
      </PageShell>
    );
  }

  return (
    <PageShell title={t('account.title')}>
      {profile.isPending ? <LoadingState title={t('account.loading')} /> : null}
      {profile.error ? (
        <ErrorState
          action={
            <button className="btn btn-sm" onClick={() => void profile.refetch()} type="button">
              {t('common.retry')}
            </button>
          }
          error={getErrorMessage(profile.error)}
          title={t('account.loadFailed')}
        />
      ) : null}
      {profile.data ? (
        <div className="grid items-start gap-6 xl:grid-cols-2">
          <Surface>
            <SurfaceHeading title={t('account.identity')} />
            <IdentityForm user={profile.data.data} />
          </Surface>
          <Surface>
            <SurfaceHeading title={t('account.password')} />
            <PasswordForm userId={profile.data.data.id} />
          </Surface>
        </div>
      ) : null}
    </PageShell>
  );
}
