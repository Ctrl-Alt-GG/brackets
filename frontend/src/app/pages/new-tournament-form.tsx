import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { addHours, startOfHour } from 'date-fns';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';

import { createTournamentApiTournamentsPostMutation } from '../../openapi/@tanstack/react-query.gen';
import { zTournamentBody } from '../../openapi/zod.gen';
import { toDateTimeLocal } from '../format';
import { zDetailsLink, zLocalDateTime } from '../forms';
import { useOrganizerTranslation } from '../organizer-locales';
import { CheckboxField, Field } from '../ui';

const newTournamentSchema = zTournamentBody.extend({
  dashboard_endpoint: zDetailsLink,
  start_time: zLocalDateTime,
});

/** A new tournament, which the organizer who creates it owns. */
export function NewTournamentForm() {
  const { t } = useOrganizerTranslation();
  const navigate = useNavigate();
  // Most tournaments start soon, on the hour. Worked out once, when the form opens.
  const [startTime] = useState(() =>
    toDateTimeLocal(addHours(startOfHour(new Date()), 1).toISOString()),
  );
  const form = useForm({
    defaultValues: {
      dashboard_endpoint: '',
      dashboard_public: true,
      duration_minutes: 30,
      margin_minutes: 5,
      name: '',
      start_time: startTime,
    },
    resolver: zodResolver(newTournamentSchema),
  });
  const create = useMutation({
    ...createTournamentApiTournamentsPostMutation(),
    meta: { successMessage: t('newTournament.created') },
  });
  const { errors } = form.formState;

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        // Straight into the new tournament, where its teams and stages are set up.
        create.mutate({ body }, { onSuccess: ({ data }) => navigate(`/tournaments/${data.id}`) }),
      )}
    >
      <Field error={errors.name?.message} label={t('common.tournamentName')}>
        <input
          className="input w-full"
          placeholder="Ctrl-Alt-GG Summer Cup"
          required
          {...form.register('name')}
        />
      </Field>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.start_time?.message} label={t('common.startTime')}>
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <Field
          error={errors.dashboard_endpoint?.message}
          hint={t('common.detailsLinkHint')}
          label={t('common.detailsLink')}
        >
          <input
            className="input w-full"
            placeholder="summer-cup-2026"
            {...form.register('dashboard_endpoint')}
          />
        </Field>
        <Field error={errors.duration_minutes?.message} label={t('common.matchDuration')}>
          <input
            className="input w-full"
            min={1}
            required
            type="number"
            {...form.register('duration_minutes', { valueAsNumber: true })}
          />
        </Field>
        <Field error={errors.margin_minutes?.message} label={t('common.breakBetweenRounds')}>
          <input
            className="input w-full"
            min={0}
            required
            type="number"
            {...form.register('margin_minutes', { valueAsNumber: true })}
          />
        </Field>
      </div>
      <div className="mt-3 grid gap-3">
        <CheckboxField
          description={t('common.detailsPageDescription')}
          label={t('newTournament.enableDetails')}
          {...form.register('dashboard_public')}
        />
      </div>
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        {create.isPending ? t('common.creating') : t('newTournament.create')}
      </button>
    </form>
  );
}
