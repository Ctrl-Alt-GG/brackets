import { format, isSameDay, isSameYear, isValid, parseISO } from 'date-fns';
import type { TFunction } from 'i18next';

import * as OpenApi from '../openapi';
import { serverNow } from './clock';
import { tournamentPhase } from './tournament-rules';

// Dates and times follow the visitor's own language settings: "15:30" where that is how a time
// is written, "3:30 PM" where that is.
const TIME_FORMAT = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });
const DATE_WITH_YEAR_FORMAT = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});
// Points have up to six decimal places, as the API stores them. Showing fewer would make
// different points look equal, while the standings still rank by the difference.
const POINTS_FORMAT = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 6,
  useGrouping: false,
});

export function formatTime(date: Date) {
  return TIME_FORMAT.format(date);
}

export function formatDateTime(value: string) {
  const date = parseISO(value);
  if (!isValid(date)) return value;
  const day = (isSameYear(date, serverNow()) ? DATE_FORMAT : DATE_WITH_YEAR_FORMAT).format(date);
  return `${day}, ${formatTime(date)}`;
}

/** Like `formatDateTime`, but an event mostly runs on one day, so today's matches show the time. */
export function formatMatchTime(value: string | null, t: TFunction) {
  if (!value) return t('time.notScheduled');
  const date = parseISO(value);
  if (!isValid(date) || !isSameDay(date, serverNow())) return formatDateTime(value);
  return t('time.today', { time: formatTime(date) });
}

/** The value of a `datetime-local` input for an ISO timestamp, in the viewer's time zone. */
export function toDateTimeLocal(value: string) {
  return format(parseISO(value), "yyyy-MM-dd'T'HH:mm");
}

export function tournamentDateLabel(tournament: OpenApi.Tournament, t: TFunction, now?: number) {
  const date = formatDateTime(tournament.start_time);
  return tournamentPhase(tournament, now) === 'upcoming'
    ? t('time.starts', { date })
    : t('time.started', { date });
}

export function formatPoints(points: string) {
  return POINTS_FORMAT.format(Number(points));
}

export function formatScoreDifference(standing: OpenApi.StageItemInputStanding) {
  return new Intl.NumberFormat(undefined, { signDisplay: 'exceptZero' }).format(
    standing.score_for - standing.score_against,
  );
}

/** Swiss stage items rank teams by an ELO rating instead of points. */
export function pointsLabel(stageItem: OpenApi.StageItemWithRounds, t: TFunction) {
  return stageItem.type === 'SWISS' ? t('points.rating') : t('points.points');
}

/** For running text, such as "2.5 points" or "rating 1216". */
export function pointsPhrase(stageItem: OpenApi.StageItemWithRounds, points: string, t: TFunction) {
  const value = formatPoints(points);
  if (stageItem.type === 'SWISS') return t('points.ratingPhrase', { value });
  return t('points.phrase', { count: Number(points), value });
}
