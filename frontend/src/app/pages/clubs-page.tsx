import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Navigate } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  createNewClubApiClubsPostMutation,
  deleteClubApiClubsClubIdDeleteMutation,
  getClubsApiClubsGetOptions,
  updateClubApiClubsClubIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zClubCreateBody, zClubUpdateBody } from '../../openapi/zod.gen';
import { useSession } from '../hooks';
import { ErrorState, Field, LoadingState, PageShell, Surface, SurfaceHeading } from '../ui';
import { formatDateTime, getErrorMessage } from '../utils';

function NewClubForm() {
  const form = useForm({ defaultValues: { name: '' }, resolver: zodResolver(zClubCreateBody) });
  const create = useMutation({
    ...createNewClubApiClubsPostMutation(),
    meta: { successMessage: 'Event created.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate({ body }, { onSuccess: () => form.reset() }),
      )}
    >
      <Field error={form.formState.errors.name?.message} label="Event name">
        <input
          className="input w-full"
          placeholder="Ctrl-Alt-GG"
          required
          {...form.register('name')}
        />
      </Field>
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        {create.isPending ? 'Creating…' : 'Create event'}
      </button>
    </form>
  );
}

function ClubEditor({ club }: { club: OpenApi.Club }) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(zClubUpdateBody),
    values: { name: club.name },
  });
  const update = useMutation({
    ...updateClubApiClubsClubIdPutMutation(),
    meta: { successMessage: 'Event saved.' },
  });
  const remove = useMutation({
    ...deleteClubApiClubsClubIdDeleteMutation(),
    meta: { successMessage: 'Event deleted.' },
  });

  return (
    <details className="collapse collapse-arrow border border-base-300 bg-base-100/50">
      <summary className="collapse-title">
        <span className="font-semibold">{club.name}</span>
        <span className="block text-sm text-base-content/70">
          Created {formatDateTime(club.created)}
        </span>
      </summary>
      <form
        className="collapse-content flex flex-col gap-3 md:flex-row md:items-end"
        onSubmit={form.handleSubmit((body) => update.mutate({ body, path: { club_id: club.id } }))}
      >
        <Field className="flex-1" error={form.formState.errors.name?.message} label="Event name">
          <input className="input w-full" required {...form.register('name')} />
        </Field>
        <div className="flex gap-2">
          <button className="btn btn-primary" disabled={update.isPending} type="submit">
            Save
          </button>
          <button
            className="btn btn-error btn-soft"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${club.name}?`)) {
                remove.mutate({ path: { club_id: club.id } });
              }
            }}
            type="button"
          >
            Delete
          </button>
        </div>
      </form>
    </details>
  );
}

export function ClubsPage() {
  const [session] = useSession();
  const clubs = useQuery({ ...getClubsApiClubsGetOptions(), enabled: Boolean(session) });

  if (!session) {
    return <Navigate replace to="/login" />;
  }

  return (
    <PageShell title="Event manager">
      <div className="grid items-start gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Surface>
          <SurfaceHeading title="New event" />
          <NewClubForm />
        </Surface>

        <Surface>
          <SurfaceHeading
            actions={
              <span className="text-sm text-base-content/70">
                {clubs.data?.data.length ?? 0} events
              </span>
            }
            title="Existing events"
          />
          {clubs.isPending ? <LoadingState title="Loading events…" /> : null}
          {clubs.error ? (
            <ErrorState
              action={
                <button className="btn btn-sm" onClick={() => void clubs.refetch()} type="button">
                  Retry
                </button>
              }
              error={getErrorMessage(clubs.error)}
              title="Unable to load events"
            />
          ) : null}
          <div className="space-y-3">
            {clubs.data?.data.map((club) => (
              <ClubEditor club={club} key={club.id} />
            ))}
          </div>
        </Surface>
      </div>
    </PageShell>
  );
}
