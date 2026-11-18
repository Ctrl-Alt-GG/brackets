import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { QRCodeSVG } from 'qrcode.react';
import { useRef } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';

import { useSavedForm } from '../saved-form';
import * as OpenApi from '../../openapi';
import {
  changeStatusApiTournamentsTournamentIdChangeStatusPostMutation,
  deleteTournamentApiTournamentsTournamentIdDeleteMutation,
  getTournamentsApiTournamentsGetQueryKey,
  updateTournamentByIdApiTournamentsTournamentIdPutMutation,
  uploadLogoApiTournamentsTournamentIdLogoPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zTournamentUpdateBody } from '../../openapi/zod.gen';
import { LogoField } from '../components/logo-field';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { confirm } from '../confirm';
import type { TournamentBundle } from '../types';
import { toDateTimeLocal } from '../format';
import {
  DETAILS_PAGE_DESCRIPTION,
  normalizeDashboardEndpoint,
  publicTournamentPath,
  tournamentLogoUrl,
} from '../urls';
import { zDetailsLink, zLocalDateTime } from '../forms';
import { CheckboxField, Field, Surface, SurfaceHeading } from '../ui';

const tournamentSettingsSchema = zTournamentUpdateBody.extend({
  dashboard_endpoint: zDetailsLink,
  start_time: zLocalDateTime,
});

function TournamentSettingsForm({ tournament }: { tournament: OpenApi.Tournament }) {
  const form = useSavedForm({
    resolver: zodResolver(tournamentSettingsSchema),
    values: {
      dashboard_endpoint: normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? '',
      dashboard_public: tournament.dashboard_public,
      duration_minutes: tournament.duration_minutes,
      margin_minutes: tournament.margin_minutes,
      name: tournament.name,
      players_can_be_in_multiple_teams: tournament.players_can_be_in_multiple_teams,
      start_time: toDateTimeLocal(tournament.start_time),
    },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateTournamentByIdApiTournamentsTournamentIdPutMutation(),
    meta: { successMessage: 'Tournament saved.' },
  });
  const uploadLogo = useMutation({
    ...uploadLogoApiTournamentsTournamentIdLogoPostMutation(),
    meta: { successMessage: 'Logo updated.' },
  });
  const path = { tournament_id: tournament.id };
  const { errors } = form.formState;
  const sharedLink = tournament.dashboard_public
    ? normalizeDashboardEndpoint(tournament.dashboard_endpoint)
    : null;

  return (
    <form
      onSubmit={form.handleSubmit(async (body) => {
        // The link is on posters and in chats by now, and nothing redirects the old one.
        if (
          sharedLink != null &&
          sharedLink !== normalizeDashboardEndpoint(body.dashboard_endpoint) &&
          !(await confirm({
            confirmLabel: 'Change the Details link',
            message: `Links and QR codes with "${sharedLink}" will stop working. Change the Details link?`,
          }))
        ) {
          return;
        }
        update.mutate({ body, path });
      })}
    >
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.name?.message} label="Tournament name">
          <input className="input w-full" required {...form.register('name')} />
        </Field>
        <Field error={errors.dashboard_endpoint?.message} label="Details link">
          <input
            className="input w-full"
            placeholder="summer-cup-2026"
            {...form.register('dashboard_endpoint')}
          />
        </Field>
        <Field error={errors.start_time?.message} label="Start time">
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <LogoField
          isPending={uploadLogo.isPending}
          label="Tournament logo"
          logoUrl={tournamentLogoUrl(tournament)}
          onChange={(file) => uploadLogo.mutate({ body: { file }, path })}
        />
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
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <CheckboxField
          description={DETAILS_PAGE_DESCRIPTION}
          label="Details page enabled"
          {...form.register('dashboard_public')}
        />
        <CheckboxField
          description="Without this, a player can only be in one team."
          label="Players can join multiple teams"
          {...form.register('players_can_be_in_multiple_teams')}
        />
      </div>
      <button className="btn btn-primary mt-4" disabled={update.isPending} type="submit">
        {update.isPending ? 'Saving…' : 'Save tournament'}
      </button>
    </form>
  );
}

/** The Details link in full, to copy into a chat or print as a QR code at the venue. */
function DetailsLink({ tournament }: { tournament: OpenApi.Tournament }) {
  const detailsUrl = new URL(publicTournamentPath(tournament), window.location.origin).href;
  const qrCode = useRef<SVGSVGElement>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(detailsUrl);
      toast.success('Link copied.');
    } catch {
      toast.error("The link couldn't be copied. Select it and copy it yourself.");
    }
  };

  // An SVG file, which prints sharp at any size.
  const download = () => {
    if (!qrCode.current) return;
    const svg = new XMLSerializer().serializeToString(qrCode.current);
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    const link = document.createElement('a');
    link.download = `${tournament.name} - Details.svg`;
    link.href = url;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-base-content/80">Share this link with players:</p>
      <div className="flex flex-wrap items-center gap-2">
        <Link className="link break-all text-sm" to={publicTournamentPath(tournament)}>
          {detailsUrl}
        </Link>
        <button className="btn btn-soft btn-sm" onClick={() => void copy()} type="button">
          Copy link
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        {/* Dark on light with a margin around it, as phone cameras read QR codes best. */}
        <QRCodeSVG
          bgColor="#ffffff"
          className="rounded-box"
          fgColor="#000000"
          marginSize={2}
          ref={qrCode}
          size={160}
          title={`QR code of ${detailsUrl}`}
          value={detailsUrl}
        />
        <button className="btn btn-ghost btn-sm" onClick={download} type="button">
          Download QR code
        </button>
      </div>
    </div>
  );
}

export function SettingsSection({ bundle }: { bundle: TournamentBundle }) {
  const navigate = useNavigate();
  const tournament = bundle.tournament;
  const isOpen = tournament.status === 'OPEN';
  const path = { tournament_id: tournament.id };
  const changeStatus = useMutation({
    ...changeStatusApiTournamentsTournamentIdChangeStatusPostMutation(),
    meta: { successMessage: isOpen ? 'Tournament archived.' : 'Tournament reopened.' },
  });
  const remove = useMutation({
    ...deleteTournamentApiTournamentsTournamentIdDeleteMutation(),
    // Reloading the deleted tournament would fail as unauthorized, which logs the organizer out.
    meta: {
      invalidates: [getTournamentsApiTournamentsGetQueryKey()],
      successMessage: 'Tournament deleted.',
    },
    onSuccess: () => navigate('/'),
  });

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[1fr_0.8fr]">
      <Surface>
        <SurfaceHeading title="Tournament settings" />
        <TournamentSettingsForm tournament={tournament} />
      </Surface>

      <Surface>
        <SurfaceHeading title="Status and sharing" />
        <section className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            Status: <TournamentStatusBadge tournament={tournament} />
          </div>
          <p className="text-sm text-base-content/70">
            {isOpen
              ? 'Archive the tournament once it is over. Archived tournaments can no longer be changed.'
              : 'This tournament is archived. Reopen it to make changes again.'}
          </p>
          <button
            className="btn btn-soft"
            disabled={changeStatus.isPending}
            onClick={async () => {
              // Archiving during an event by mistake would take the tournament away from players.
              if (
                isOpen &&
                !(await confirm({
                  confirmLabel: 'Archive tournament',
                  message: tournament.dashboard_public
                    ? `Archive ${tournament.name}? It can't be changed until it is reopened. Players can still follow it on its Details page.`
                    : `Archive ${tournament.name}? Players can no longer see it, because its Details page isn't enabled, and it can't be changed until it is reopened.`,
                }))
              ) {
                return;
              }
              changeStatus.mutate({ body: { status: isOpen ? 'ARCHIVED' : 'OPEN' }, path });
            }}
            type="button"
          >
            {isOpen ? 'Archive tournament' : 'Reopen tournament'}
          </button>
        </section>

        <section className="space-y-2 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">Details page</h3>
          {tournament.dashboard_public ? (
            <DetailsLink tournament={tournament} />
          ) : (
            <p className="text-sm text-base-content/70">
              Turn on “Details page enabled” to share a link to it, and to keep it visible after the
              tournament is archived.
            </p>
          )}
        </section>

        <section className="space-y-3 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">Delete tournament</h3>
          <p className="text-sm text-base-content/70">
            Deletes the tournament with its teams, players and results. This cannot be undone.
          </p>
          <button
            className="btn btn-error"
            disabled={remove.isPending}
            onClick={async () => {
              if (
                await confirm({
                  confirmLabel: 'Delete tournament',
                  destructive: true,
                  message: `Delete ${tournament.name}? This cannot be undone.`,
                })
              ) {
                remove.mutate({ path });
              }
            }}
            type="button"
          >
            Delete tournament
          </button>
        </section>
      </Surface>
    </div>
  );
}
