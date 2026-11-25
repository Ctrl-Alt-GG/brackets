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
import { zTournamentBody } from '../../openapi/zod.gen';
import { LogoField } from '../components/logo-field';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { confirm } from '../confirm';
import type { TournamentBundle } from '../types';
import { toDateTimeLocal } from '../format';
import { normalizeDashboardEndpoint, publicTournamentPath, tournamentLogoUrl } from '../urls';
import { zDetailsLink, zLocalDateTime } from '../forms';
import { useOrganizerTranslation } from '../organizer-locales';
import { CheckboxField, Field, SaveButton, Surface, SurfaceHeading } from '../ui';
import { OrganizersSection, useOrganizers } from './tournament-organizers';

const tournamentSettingsSchema = zTournamentBody.extend({
  dashboard_endpoint: zDetailsLink,
  start_time: zLocalDateTime,
});

function TournamentSettingsForm({ tournament }: { tournament: OpenApi.Tournament }) {
  const { t } = useOrganizerTranslation();
  const form = useSavedForm({
    resolver: zodResolver(tournamentSettingsSchema),
    values: {
      dashboard_endpoint: normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? '',
      dashboard_public: tournament.dashboard_public,
      duration_minutes: tournament.duration_minutes,
      margin_minutes: tournament.margin_minutes,
      name: tournament.name,
      start_time: toDateTimeLocal(tournament.start_time),
    },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateTournamentByIdApiTournamentsTournamentIdPutMutation(),
    meta: { successMessage: t('settings.saved') },
  });
  const uploadLogo = useMutation({
    ...uploadLogoApiTournamentsTournamentIdLogoPostMutation(),
    meta: { successMessage: t('common.logoUpdated') },
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
            confirmLabel: t('settings.changeLink'),
            message: t('settings.changeLinkQuestion', { link: sharedLink }),
          }))
        ) {
          return;
        }
        update.mutate({ body, path });
      })}
    >
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.name?.message} label={t('common.tournamentName')}>
          <input className="input w-full" required {...form.register('name')} />
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
        <Field error={errors.start_time?.message} label={t('common.startTime')}>
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <LogoField
          isPending={uploadLogo.isPending}
          label={t('settings.logo')}
          logoUrl={tournamentLogoUrl(tournament)}
          onChange={(file) => uploadLogo.mutate({ body: { file }, path })}
        />
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
      <CheckboxField
        className="mt-3"
        description={t('common.detailsPageDescription')}
        label={t('settings.detailsEnabled')}
        {...form.register('dashboard_public')}
      />
      <SaveButton className="mt-4" dirty={form.formState.isDirty} disabled={update.isPending}>
        {update.isPending ? t('common.saving') : t('settings.save')}
      </SaveButton>
    </form>
  );
}

/** The Details link in full, to copy into a chat or print as a QR code at the venue. */
function DetailsLink({ tournament }: { tournament: OpenApi.Tournament }) {
  const { t } = useOrganizerTranslation();
  const detailsUrl = new URL(publicTournamentPath(tournament), window.location.origin).href;
  const qrCode = useRef<SVGSVGElement>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(detailsUrl);
      toast.success(t('settings.linkCopied'));
    } catch {
      toast.error(t('settings.copyFailed'));
    }
  };

  // An SVG file, which prints sharp at any size.
  const download = () => {
    if (!qrCode.current) return;
    const svg = new XMLSerializer().serializeToString(qrCode.current);
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    const link = document.createElement('a');
    link.download = t('settings.qrCodeFile', { name: tournament.name });
    link.href = url;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-base-content/80">{t('settings.shareLink')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Link className="link break-all text-sm" to={publicTournamentPath(tournament)}>
          {detailsUrl}
        </Link>
        <button className="btn btn-soft btn-sm" onClick={() => void copy()} type="button">
          {t('settings.copyLink')}
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
          title={t('settings.qrCodeOf', { url: detailsUrl })}
          value={detailsUrl}
        />
        <button className="btn btn-ghost btn-sm" onClick={download} type="button">
          {t('settings.downloadQrCode')}
        </button>
      </div>
    </div>
  );
}

export function SettingsSection({ bundle }: { bundle: TournamentBundle }) {
  const { t } = useOrganizerTranslation();
  const navigate = useNavigate();
  const tournament = bundle.tournament;
  const { isOwner, organizers } = useOrganizers(tournament.id);
  const isOpen = tournament.status === 'OPEN';
  const path = { tournament_id: tournament.id };
  const changeStatus = useMutation({
    ...changeStatusApiTournamentsTournamentIdChangeStatusPostMutation(),
    meta: { successMessage: isOpen ? t('settings.archived') : t('settings.reopened') },
  });
  const remove = useMutation({
    ...deleteTournamentApiTournamentsTournamentIdDeleteMutation(),
    // Reloading the deleted tournament would fail as unauthorized, which logs the organizer out.
    meta: {
      invalidates: [getTournamentsApiTournamentsGetQueryKey()],
      successMessage: t('settings.deleted'),
    },
    onSuccess: () => navigate('/'),
  });

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[1fr_0.8fr]">
      <Surface>
        <SurfaceHeading title={t('settings.title')} />
        <TournamentSettingsForm tournament={tournament} />
      </Surface>

      <Surface>
        <SurfaceHeading title={t('settings.statusAndSharing')} />
        <section className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            {t('settings.status')} <TournamentStatusBadge tournament={tournament} />
          </div>
          <p className="text-sm text-base-content/70">
            {isOpen ? t('settings.archiveHint') : t('settings.archivedHint')}
          </p>
          <button
            className="btn btn-soft"
            disabled={changeStatus.isPending}
            onClick={async () => {
              // Archiving during an event by mistake would take the tournament away from players.
              if (
                isOpen &&
                !(await confirm({
                  confirmLabel: t('settings.archive'),
                  message: tournament.dashboard_public
                    ? t('settings.archiveQuestionPublic', { name: tournament.name })
                    : t('settings.archiveQuestionPrivate', { name: tournament.name }),
                }))
              ) {
                return;
              }
              changeStatus.mutate({ body: { status: isOpen ? 'ARCHIVED' : 'OPEN' }, path });
            }}
            type="button"
          >
            {isOpen ? t('settings.archive') : t('settings.reopen')}
          </button>
        </section>

        <section className="space-y-2 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">{t('settings.detailsPage')}</h3>
          {tournament.dashboard_public ? (
            <DetailsLink tournament={tournament} />
          ) : (
            <p className="text-sm text-base-content/70">
              {t('settings.detailsDisabled', { option: t('settings.detailsEnabled') })}
            </p>
          )}
        </section>

        <OrganizersSection isOwner={isOwner} organizers={organizers} tournament={tournament} />

        <section className="space-y-3 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">{t('settings.deleteTitle')}</h3>
          <p className="text-sm text-base-content/70">{t('settings.deleteHint')}</p>
          {isOwner ? (
            <button
              className="btn btn-error"
              disabled={remove.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    confirmLabel: t('settings.deleteTitle'),
                    destructive: true,
                    message: t('settings.deleteQuestion', { name: tournament.name }),
                  })
                ) {
                  remove.mutate({ path });
                }
              }}
              type="button"
            >
              {t('settings.deleteTitle')}
            </button>
          ) : (
            <p className="text-sm text-base-content/70">{t('settings.deleteOwnerOnly')}</p>
          )}
        </section>
      </Surface>
    </div>
  );
}
