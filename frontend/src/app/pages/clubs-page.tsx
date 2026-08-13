import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router';

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
  const [nameError, setNameError] = useState<string | null>(null);

  if (!session) {
    return <Navigate replace to="/login" />;
  }

  function findDuplicate(name: string, ignoreClubId?: number) {
    const normalized = name.trim().toLocaleLowerCase();
    return clubs.data?.some(
      (club) => club.id !== ignoreClubId && club.name.trim().toLocaleLowerCase() === normalized,
    );
  }

  async function createClub(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const name = String(formData.get('name') ?? '');

    if (findDuplicate(name)) {
      setNameError('An event with this name already exists.');
      return;
    }
    setNameError(null);

    await runAction(
      setFlash,
      async () => {
        await OpenApi.createNewClubApiClubsPost({
          body: { name },
          throwOnError: true,
        });
      },
      'Event created successfully.',
      () => {
        form.reset();
        clubs.refresh();
      },
    );
  }

  return (
    <PageShell title="Event manager">
      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Surface className="space-y-4">
          <SurfaceHeading title="New event" />
          <form className="space-y-4" onSubmit={createClub}>
            <FormField error={nameError} label="Event name">
              <Input
                name="name"
                onChange={() => setNameError(null)}
                placeholder="Ctrl-Alt-GG"
                required
              />
            </FormField>
            <Button type="submit">Create event</Button>
          </form>
        </Surface>

        <Surface className="space-y-4">
          <SurfaceHeading
            actions={<Pill>{`${clubs.data?.length ?? 0} events`}</Pill>}
            title="Existing events"
          />
          {clubs.loading ? <LoadingState title="Loading events…" /> : null}
          {clubs.error ? (
            <ErrorState
              error={clubs.error}
              title="Unable to load events"
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
                    const name = String(formData.get('name') ?? '');

                    if (findDuplicate(name, club.id)) {
                      setFlash({
                        text: 'An event with this name already exists.',
                        tone: 'error',
                      });
                      return;
                    }

                    await runAction(
                      setFlash,
                      async () => {
                        await OpenApi.updateClubApiClubsClubIdPut({
                          body: { name },
                          path: { club_id: club.id },
                          throwOnError: true,
                        });
                      },
                      'Event updated successfully.',
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
                          'Event deleted successfully.',
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
