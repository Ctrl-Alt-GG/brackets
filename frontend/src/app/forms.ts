import { z } from 'zod';

import { organizerT } from './organizer-locales';

/** A `datetime-local` value, sent as the UTC timestamp the API expects. */
export const zLocalDateTime = z
  .string()
  .min(1, { error: () => organizerT('validation.pickDateTime') })
  .transform((value) => new Date(value).toISOString());

/**
 * A tournament's Details link: the same rule as the API's, checked while it is typed. It is
 * lowercase like the stored one, so that typing it with capitals doesn't count as a change.
 */
export const zDetailsLink = z
  .string()
  .trim()
  .toLowerCase()
  .max(64, { error: () => organizerT('validation.detailsLinkTooLong') })
  .regex(/^([A-Za-z0-9_-]*[A-Za-z][A-Za-z0-9_-]*)?$/, {
    error: () => organizerT('validation.detailsLinkCharacters'),
  });
