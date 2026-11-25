import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  addTournamentOrganizerApiTournamentsTournamentIdOrganizersPostMutation,
  getTournamentOrganizersApiTournamentsTournamentIdOrganizersGetOptions,
  getTournamentsApiTournamentsGetQueryKey,
  removeTournamentOrganizerApiTournamentsTournamentIdOrganizersUserIdDeleteMutation,
  transferTournamentOwnershipApiTournamentsTournamentIdOwnerPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zOrganizerCreateBody } from '../../openapi/zod.gen';
import { confirm } from '../confirm';
import { useCreateForm } from '../create-form';
import { getErrorMessage } from '../errors';
import { useSession } from '../hooks';
import { useOrganizerTranslation } from '../organizer-locales';
import { ErrorState, Field } from '../ui';

/** Who runs the tournament, and whether the one signed in owns it. */
export function useOrganizers(tournamentId: number) {
  const [session] = useSession();
  const organizers = useQuery(
    getTournamentOrganizersApiTournamentsTournamentIdOrganizersGetOptions({
      path: { tournament_id: tournamentId },
    }),
  );
  const isOwner =
    organizers.data?.data.some(
      (organizer) => organizer.user_id === session?.user_id && organizer.role === 'OWNER',
    ) ?? false;
  return { isOwner, organizers };
}

function AddOrganizerForm({ tournamentId }: { tournamentId: number }) {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm({
    defaultValues: { email: '' },
    resolver: zodResolver(zOrganizerCreateBody),
  });
  const add = useMutation({
    ...addTournamentOrganizerApiTournamentsTournamentIdOrganizersPostMutation(),
    meta: { successMessage: t('organizers.added') },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        add.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field
          error={form.formState.errors.email?.message}
          hint={t('organizers.needsAccount')}
          label={t('organizers.addByEmail')}
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
        <button className="btn mt-4" type="submit">
          {add.isPending ? t('common.adding') : t('organizers.add')}
        </button>
      </fieldset>
    </form>
  );
}

function OrganizerRow({
  isOwner,
  organizer,
  tournament,
}: {
  isOwner: boolean;
  organizer: OpenApi.Organizer;
  tournament: OpenApi.Tournament;
}) {
  const { t } = useOrganizerTranslation();
  const navigate = useNavigate();
  const [session] = useSession();
  const path = { tournament_id: tournament.id };
  const remove = useMutation({
    ...removeTournamentOrganizerApiTournamentsTournamentIdOrganizersUserIdDeleteMutation(),
    meta: { successMessage: t('organizers.removed') },
  });
  // Someone who left can't load the tournament's organizer pages any more.
  const leave = useMutation({
    ...removeTournamentOrganizerApiTournamentsTournamentIdOrganizersUserIdDeleteMutation(),
    meta: {
      invalidates: [getTournamentsApiTournamentsGetQueryKey()],
      successMessage: t('organizers.left'),
    },
    onSuccess: () => navigate('/'),
  });
  const handOver = useMutation({
    ...transferTournamentOwnershipApiTournamentsTournamentIdOwnerPutMutation(),
    meta: { successMessage: t('organizers.newOwner') },
  });
  const isMe = organizer.user_id === session?.user_id;
  const isTheOwner = organizer.role === 'OWNER';

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
      <div className="min-w-0">
        <p className="font-medium">
          {organizer.name}
          {isMe ? <span className="text-base-content/70"> {t('organizers.you')}</span> : null}
        </p>
        <p className="truncate text-sm text-base-content/70">
          {isTheOwner ? t('organizers.owner') : t('organizers.organizer')} · {organizer.email}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {isOwner && !isTheOwner ? (
          <button
            className="btn btn-soft btn-sm"
            disabled={handOver.isPending}
            onClick={async () => {
              if (
                await confirm({
                  confirmLabel: t('organizers.makeOwner'),
                  message: t('organizers.makeOwnerQuestion', {
                    member: organizer.name,
                    tournament: tournament.name,
                  }),
                })
              ) {
                handOver.mutate({ body: { user_id: organizer.user_id }, path });
              }
            }}
            type="button"
          >
            {t('organizers.makeOwner')}
          </button>
        ) : null}
        {!isTheOwner && (isOwner || isMe) ? (
          <button
            className="btn btn-error btn-soft btn-sm"
            disabled={remove.isPending || leave.isPending}
            onClick={async () => {
              const question = isMe
                ? t('organizers.leaveQuestion', { tournament: tournament.name })
                : t('organizers.removeQuestion', {
                    member: organizer.name,
                    tournament: tournament.name,
                  });
              if (
                await confirm({
                  confirmLabel: isMe ? t('organizers.leaveTournament') : t('organizers.remove'),
                  destructive: true,
                  message: question,
                })
              ) {
                (isMe ? leave : remove).mutate({ path: { ...path, user_id: organizer.user_id } });
              }
            }}
            type="button"
          >
            {isMe ? t('organizers.leave') : t('common.remove')}
          </button>
        ) : null}
      </div>
    </li>
  );
}

/**
 * Who runs the tournament: its owner, and the organizers the owner added, so that nobody shares a
 * login. Only the owner decides who helps.
 */
export function OrganizersSection({
  isOwner,
  organizers,
  tournament,
}: {
  isOwner: boolean;
  organizers: ReturnType<typeof useOrganizers>['organizers'];
  tournament: OpenApi.Tournament;
}) {
  const { t } = useOrganizerTranslation();

  return (
    <section className="space-y-3 border-t border-base-300 pt-5">
      <div>
        <h3 className="text-sm font-medium">{t('organizers.title')}</h3>
        <p className="text-sm text-base-content/70">{t('organizers.help')}</p>
      </div>
      {organizers.data ? (
        <ul className="divide-y divide-base-300 rounded-box border border-base-300">
          {organizers.data.data.map((organizer) => (
            <OrganizerRow
              isOwner={isOwner}
              key={organizer.user_id}
              organizer={organizer}
              tournament={tournament}
            />
          ))}
        </ul>
      ) : organizers.error ? (
        <ErrorState
          action={
            <button className="btn btn-sm" onClick={() => void organizers.refetch()} type="button">
              {t('common.retry')}
            </button>
          }
          error={getErrorMessage(organizers.error)}
          title={t('organizers.loadFailed')}
        />
      ) : (
        <p className="text-sm text-base-content/70" role="status">
          {t('organizers.loading')}
        </p>
      )}
      {isOwner ? <AddOrganizerForm tournamentId={tournament.id} /> : null}
    </section>
  );
}
