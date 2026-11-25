import { format, isSameDay, isSameYear, isValid, parseISO } from 'date-fns';
import type { TFunction } from 'i18next';
import { getI18n } from 'react-i18next';

import * as OpenApi from '../openapi';
import { serverNow } from './clock';
import { tournamentPhase } from './tournament-rules';

function createFormats(locale: string) {
  const time = { hour: 'numeric', minute: '2-digit' } as const;
  return {
    dateTime: new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', ...time }),
    dateTimeWithYear: new Intl.DateTimeFormat(locale, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      ...time,
    }),
    // Points have up to six decimal places, as the API stores them. Showing fewer would make
    // different points look equal, while the standings still rank by the difference.
    points: new Intl.NumberFormat(locale, { maximumFractionDigits: 6, useGrouping: false }),
    scoreDifference: new Intl.NumberFormat(locale, { signDisplay: 'exceptZero' }),
    time: new Intl.DateTimeFormat(locale, time),
  };
}

const formatsByLocale = new Map<string, ReturnType<typeof createFormats>>();

/**
 * Dates and numbers are written in the language of the page, with the visitor's own conventions
 * where their browser uses that language: "15:30" where that is how a time is written, "3:30 PM"
 * where that is.
 */
function formats() {
  const language = getI18n()?.resolvedLanguage ?? 'en';
  const preferred = typeof navigator === 'undefined' ? [] : navigator.languages;
  const locale = preferred.find((tag) => tag.split('-')[0] === language) ?? language;
  let result = formatsByLocale.get(locale);
  if (!result) {
    result = createFormats(locale);
    formatsByLocale.set(locale, result);
  }
  return result;
}

export function formatTime(date: Date) {
  return formats().time.format(date);
}

export function formatDateTime(value: string) {
  const date = parseISO(value);
  if (!isValid(date)) return value;
  const { dateTime, dateTimeWithYear } = formats();
  return (isSameYear(date, serverNow()) ? dateTime : dateTimeWithYear).format(date);
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
  return formats().points.format(Number(points));
}

export function formatScoreDifference(standing: OpenApi.StageItemInputStanding) {
  return formats().scoreDifference.format(standing.score_for - standing.score_against);
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
