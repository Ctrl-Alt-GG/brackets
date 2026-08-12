import type { FormEvent } from 'react';
import { Link, Navigate } from 'react-router';

import * as OpenApi from '../../openapi';
import { unwrap } from '../api';
import { runAction, useResource } from '../hooks';
import type { FlashMessage, Session } from '../types';
import { formatDateTime } from '../utils';
import { Button, EmptyState, ErrorState, FormField, Input, PageShell, Pill, Surface } from '../ui';

export function ClubsPage({
  session,
  setFlash,
}: {
  session: Session;
  setFlash: (message: FlashMessage) => void;
}) {
  const clubs = useResource(
    async () => {
      const response = await unwrap(OpenApi.getClubsApiClubsGet({ throwOnError: true }));
      return response.data;
    },
    [session?.access_token],
    Boolean(session),
  );

  if (!session) {
    return <Navigate replace to="/login" />;
  }

  async function createClub(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    await runAction(
      setFlash,
      async () => {
        await OpenApi.createNewClubApiClubsPost({
          body: { name: String(formData.get('name') ?? '') },
          throwOnError: true,
        });
      },
      'Club created successfully.',
      () => {
        form.reset();
        clubs.refresh();
      },
    );
  }

  return (
    <PageShell title="Club manager">
      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Surface className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Create
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">New club</h2>
          </div>
          <form className="space-y-4" onSubmit={createClub}>
            <FormField label="Club name">
              <Input name="name" placeholder="Ctrl-Alt-GG" required />
            </FormField>
            <Button type="submit">Create club</Button>
          </form>
        </Surface>

        <Surface className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                Inventory
              </p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-white">
                Existing clubs
              </h2>
            </div>
            <Pill>{`${clubs.data?.length ?? 0} clubs`}</Pill>
          </div>
          {clubs.loading ? <div className="hidden" /> : null}
          {clubs.error ? (
            <ErrorState
              error={clubs.error}
              title="Unable to load clubs"
              action={
                <Button onClick={clubs.refresh} type="button">
                  Retry
                </Button>
              }
            />
          ) : null}
          <div className="space-y-4">
            {clubs.data?.map((club) => (
              <details
                className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
                key={club.id}
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-white">{club.name}</h3>
                    <p className="text-sm text-zinc-400">Created {formatDateTime(club.created)}</p>
                  </div>
                  <Pill>#{club.id}</Pill>
                </summary>
                <form
                  className="mt-4 flex flex-col gap-3 md:flex-row"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    const formData = new FormData(event.currentTarget);
                    await runAction(
                      setFlash,
                      async () => {
                        await OpenApi.updateClubApiClubsClubIdPut({
                          body: { name: String(formData.get('name') ?? '') },
                          path: { club_id: club.id },
                          throwOnError: true,
                        });
                      },
                      'Club updated successfully.',
                      clubs.refresh,
                    );
                  }}
                >
                  <Input defaultValue={club.name} name="name" />
                  <div className="flex gap-3">
                    <Button type="submit">Save</Button>
                    <Button
                      onClick={async () => {
                        if (!window.confirm(`Delete ${club.name}?`)) return;
                        await runAction(
                          setFlash,
                          async () => {
                            await OpenApi.deleteClubApiClubsClubIdDelete({
                              path: { club_id: club.id },
                              throwOnError: true,
                            });
                          },
                          'Club deleted successfully.',
                          clubs.refresh,
                        );
                      }}
                      tone="danger"
                      type="button"
                    >
                      Delete
                    </Button>
                  </div>
                </form>
              </details>
            ))}
          </div>
        </Surface>
      </div>
    </PageShell>
  );
}
