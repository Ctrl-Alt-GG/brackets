import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';

import * as OpenApi from '../../openapi';
import { createTournamentApiTournamentsPostMutation } from '../../openapi/@tanstack/react-query.gen';
import { zTournamentBody } from '../../openapi/zod.gen';
import { zDetailsLink, zLocalDateTime } from '../forms';
import { CheckboxField, Field } from '../ui';
import { DETAILS_PAGE_DESCRIPTION } from '../utils';

const newTournamentSchema = zTournamentBody.extend({
  dashboard_endpoint: zDetailsLink,
  start_time: zLocalDateTime,
});

export function NewTournamentForm({ clubs }: { clubs: OpenApi.Club[] }) {
  const navigate = useNavigate();
  const form = useForm({
    defaultValues: {
      club_id: clubs[0]?.id,
      dashboard_endpoint: '',
      dashboard_public: true,
      duration_minutes: 30,
      margin_minutes: 5,
      name: '',
      players_can_be_in_multiple_teams: false,
      start_time: '',
    },
    resolver: zodResolver(newTournamentSchema),
  });
  const create = useMutation({
    ...createTournamentApiTournamentsPostMutation(),
    meta: { successMessage: 'Tournament created.' },
  });
  const { errors } = form.formState;

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        // Straight into the new tournament, where its teams and stages are set up.
        create.mutate({ body }, { onSuccess: ({ data }) => navigate(`/tournaments/${data.id}`) }),
      )}
    >
      <Field error={errors.name?.message} label="Tournament name">
        <input
          className="input w-full"
          placeholder="Ctrl-Alt-GG Summer Cup"
          required
          {...form.register('name')}
        />
      </Field>
      <Field label="Event">
        <select
          className="select w-full"
          required
          {...form.register('club_id', { valueAsNumber: true })}
        >
          {clubs.map((club) => (
            <option key={club.id} value={club.id}>
              {club.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.start_time?.message} label="Start time">
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <Field error={errors.dashboard_endpoint?.message} label="Details link">
          <input
            className="input w-full"
            placeholder="summer-cup-2026"
            {...form.register('dashboard_endpoint')}
          />
        </Field>
        <Field error={errors.duration_minutes?.message} label="Match duration (minutes)">
          <input
            className="input w-full"
            min={1}
            required
            type="number"
            {...form.register('duration_minutes', { valueAsNumber: true })}
          />
        </Field>
        <Field error={errors.margin_minutes?.message} label="Break between rounds (minutes)">
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
          description={DETAILS_PAGE_DESCRIPTION}
          label="Enable the Details page"
          {...form.register('dashboard_public')}
        />
        <CheckboxField
          description="Without this, a player can only be in one team."
          label="Allow players in multiple teams"
          {...form.register('players_can_be_in_multiple_teams')}
        />
      </div>
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        {create.isPending ? 'Creating…' : 'Create tournament'}
      </button>
    </form>
  );
}
