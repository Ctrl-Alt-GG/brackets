import { Link } from 'react-router';
import type { FormEvent } from 'react';

import * as OpenApi from '../../openapi';
import { unwrap } from '../api';
import { runAction, useResource } from '../hooks';
import type { FlashMessage, Session } from '../types';
import { formatDateTime } from '../utils';
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageShell,
  Pill,
  Surface,
  SurfaceHeading,
} from '../ui';

export function UserPage({
  session,
  setFlash,
}: {
  session: Session;
  setFlash: (message: FlashMessage) => void;
}) {
  const profile = useResource(
    async () => {
      const response = await unwrap(
        OpenApi.getUserApiUsersMeGet({
          auth: session?.access_token,
          throwOnError: true,
        }),
      );
      return response.data;
    },
    [session?.access_token],
    Boolean(session),
  );

  if (!session) {
    return (
      <PageShell title="Account">
        <EmptyState
          text="Log in first to view or update your account."
          title="Authentication required"
          action={
            <Link
              className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
              to="/login"
            >
              Log in
            </Link>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Account">
      {profile.loading ? <LoadingState title="Loading account…" /> : null}
      {profile.error ? (
        <ErrorState
          error={profile.error}
          title="Unable to load account"
          action={
            <Button onClick={profile.refresh} type="button">
              Retry
            </Button>
          }
        />
      ) : null}
      {profile.data
        ? (() => {
            const profileData = profile.data;

            return (
              <div className="grid gap-6 xl:grid-cols-2">
                <Surface className="space-y-4">
                  <SurfaceHeading title="Identity" />
                  <form
                    className="space-y-4"
                    onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      const formData = new FormData(event.currentTarget);
                      await runAction(
                        setFlash,
                        async () => {
                          await OpenApi.updateUserDetailsApiUsersUserIdPut({
                            body: {
                              email: String(formData.get('email') ?? ''),
                              name: String(formData.get('name') ?? ''),
                            },
                            path: { user_id: profileData.id },
                            throwOnError: true,
                          });
                        },
                        'Account updated successfully.',
                        profile.refresh,
                      );
                    }}
                  >
                    <FormField label="Display name">
                      <Input defaultValue={profileData.name} name="name" required />
                    </FormField>
                    <FormField label="Email">
                      <Input defaultValue={profileData.email} name="email" required type="email" />
                    </FormField>
                    <div className="flex items-center gap-3 text-sm text-zinc-400">
                      <Pill tone="success">{profileData.account_type}</Pill>
                      <span>Created {formatDateTime(profileData.created)}</span>
                    </div>
                    <Button type="submit">Save profile</Button>
                  </form>
                </Surface>

                <Surface className="space-y-4">
                  <SurfaceHeading title="Password" />
                  <form
                    className="space-y-4"
                    onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      const formData = new FormData(event.currentTarget);
                      const password = String(formData.get('password') ?? '');
                      if (password.length < 8) {
                        setFlash({
                          text: 'Password must contain at least eight characters.',
                          tone: 'error',
                        });
                        return;
                      }

                      await runAction(
                        setFlash,
                        async () => {
                          await OpenApi.putUserPasswordApiUsersUserIdPasswordPut({
                            body: { password },
                            path: { user_id: profileData.id },
                            throwOnError: true,
                          });
                        },
                        'Password updated successfully.',
                        () => event.currentTarget.reset(),
                      );
                    }}
                  >
                    <FormField label="New password">
                      <Input
                        minLength={8}
                        name="password"
                        placeholder="At least eight characters"
                        required
                        type="password"
                      />
                    </FormField>
                    <Button type="submit">Update password</Button>
                  </form>
                </Surface>
              </div>
            );
          })()
        : null}
    </PageShell>
  );
}
