import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  addMemberApiClubsClubIdMembersPostMutation,
  createNewClubApiClubsPostMutation,
  deleteClubApiClubsClubIdDeleteMutation,
  getClubsApiClubsGetOptions,
  getClubsApiClubsGetQueryKey,
  getMembersApiClubsClubIdMembersGetOptions,
  removeMemberApiClubsClubIdMembersUserIdDeleteMutation,
  updateClubApiClubsClubIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zClubCreateBody, zClubMemberCreateBody, zClubUpdateBody } from '../../openapi/zod.gen';
import { useSession } from '../hooks';
import { useSavedForm } from '../saved-form';
import { ErrorState, Field, LoadingState, PageShell, Surface, SurfaceHeading } from '../ui';
import { formatDateTime, getErrorMessage, loginPath } from '../utils';

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

/** Renaming and deleting an event, which only its owner can do. */
function ClubNameForm({ club }: { club: OpenApi.Club }) {
  const form = useSavedForm({
    resolver: zodResolver(zClubUpdateBody),
    values: { name: club.name },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateClubApiClubsClubIdPutMutation(),
    meta: { successMessage: 'Event saved.' },
  });
  const remove = useMutation({
    ...deleteClubApiClubsClubIdDeleteMutation(),
    // The event is gone, so asking for its organizers again would only fail.
    meta: { invalidates: [getClubsApiClubsGetQueryKey()], successMessage: 'Event deleted.' },
  });

  return (
    <form
      className="flex flex-col gap-3 md:flex-row md:items-end"
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
  );
}

/** Who runs an event: its owner, and the organizers the owner added so nobody shares a login. */
function ClubMembers({
  club,
  isOwner,
  members,
  userId,
}: {
  club: OpenApi.Club;
  isOwner: boolean;
  members: OpenApi.ClubMember[];
  userId: number;
}) {
  const form = useForm({
    defaultValues: { email: '' },
    resolver: zodResolver(zClubMemberCreateBody),
  });
  const add = useMutation({
    ...addMemberApiClubsClubIdMembersPostMutation(),
    meta: { successMessage: 'Organizer added.' },
  });
  const remove = useMutation({
    ...removeMemberApiClubsClubIdMembersUserIdDeleteMutation(),
    meta: { successMessage: 'Organizer removed.' },
  });
  const leave = useMutation({
    ...removeMemberApiClubsClubIdMembersUserIdDeleteMutation(),
    // Someone who left can't ask who the organizers are any more.
    meta: { invalidates: [getClubsApiClubsGetQueryKey()], successMessage: 'You left the event.' },
  });
  const path = { club_id: club.id };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="font-semibold">Organizers</h3>
        <p className="text-sm text-base-content/70">
          Everyone here can manage the tournaments of this event. Only the owner can rename or
          delete the event and decide who helps.
        </p>
      </div>
      <ul className="divide-y divide-base-300 rounded-box border border-base-300">
        {members.map((member) => {
          const isMe = member.user_id === userId;
          const canRemove = member.relation !== 'OWNER' && (isOwner || isMe);

          return (
            <li
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3"
              key={member.user_id}
            >
              <div className="min-w-0">
                <p className="font-medium">
                  {member.name}
                  {isMe ? <span className="text-base-content/70"> (you)</span> : null}
                </p>
                <p className="truncate text-sm text-base-content/70">
                  {member.relation === 'OWNER' ? 'Owner' : 'Organizer'} · {member.email}
                </p>
              </div>
              {canRemove ? (
                <button
                  className="btn btn-error btn-soft btn-sm"
                  disabled={remove.isPending || leave.isPending}
                  onClick={() => {
                    const question = isMe
                      ? `Leave ${club.name}? You lose access to its tournaments.`
                      : `Remove ${member.name} from ${club.name}? They lose access to its tournaments.`;
                    if (!window.confirm(question)) return;
                    (isMe ? leave : remove).mutate({
                      path: { ...path, user_id: member.user_id },
                    });
                  }}
                  type="button"
                >
                  {isMe ? 'Leave' : 'Remove'}
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
      {isOwner ? (
        <form
          className="flex flex-col gap-3 md:flex-row md:items-end"
          onSubmit={form.handleSubmit((body) =>
            add.mutate({ body, path }, { onSuccess: () => form.reset() }),
          )}
        >
          <Field
            className="flex-1"
            error={form.formState.errors.email?.message}
            hint="They need an account on this site first."
            label="Add an organizer by email"
          >
            <input
              autoComplete="off"
              className="input w-full"
              placeholder="organizer@example.org"
              required
              type="email"
              {...form.register('email')}
            />
          </Field>
          <button className="btn" disabled={add.isPending} type="submit">
            {add.isPending ? 'Adding…' : 'Add organizer'}
          </button>
        </form>
      ) : null}
    </div>
  );
}

function ClubEditor({ club, userId }: { club: OpenApi.Club; userId: number }) {
  // The organizers are only loaded for the event that is opened.
  const [isOpen, setIsOpen] = useState(false);
  const members = useQuery({
    ...getMembersApiClubsClubIdMembersGetOptions({ path: { club_id: club.id } }),
    enabled: isOpen,
  });
  const isOwner =
    members.data?.data.some((member) => member.user_id === userId && member.relation === 'OWNER') ??
    false;

  return (
    <details
      className="collapse collapse-arrow border border-base-300 bg-base-100/50"
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
    >
      <summary className="collapse-title">
        <span className="font-semibold">{club.name}</span>
        <span className="block text-sm text-base-content/70">
          Created {formatDateTime(club.created)}
        </span>
      </summary>
      <div className="collapse-content space-y-5">
        {members.data ? (
          <>
            {isOwner ? <ClubNameForm club={club} /> : null}
            <ClubMembers
              club={club}
              isOwner={isOwner}
              members={members.data.data}
              userId={userId}
            />
          </>
        ) : members.error ? (
          <ErrorState
            action={
              <button className="btn btn-sm" onClick={() => void members.refetch()} type="button">
                Retry
              </button>
            }
            error={getErrorMessage(members.error)}
            title="Unable to load this event"
          />
        ) : (
          <p className="text-sm text-base-content/70" role="status">
            Loading…
          </p>
        )}
      </div>
    </details>
  );
}

export function ClubsPage() {
  const [session] = useSession();
  const clubs = useQuery({ ...getClubsApiClubsGetOptions(), enabled: Boolean(session) });

  if (!session) {
    return <Navigate replace to={loginPath('/events')} />;
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
              <ClubEditor club={club} key={club.id} userId={session.user_id} />
            ))}
          </div>
        </Surface>
      </div>
    </PageShell>
  );
}
