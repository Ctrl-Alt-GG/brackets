/* Match statuses follow the server's clock. A phone whose clock is a few minutes off would
   otherwise show the wrong matches as playing now. Every answer of the API says when the server
   sent it; the difference to this device's clock is kept and applied wherever a page compares a
   time with now. */

import { useInterval } from '@mantine/hooks';
import { useState } from 'react';

let offsetMs = 0;

/**
 * Note the server's time from the `Date` header of an answer that arrived just now. The header
 * has whole seconds, so the half second it drops on average is added back.
 */
export function syncClock(dateHeader: unknown, receivedAt: number = Date.now()) {
  const server = typeof dateHeader === 'string' ? Date.parse(dateHeader) : Number.NaN;
  if (Number.isFinite(server)) offsetMs = server + 500 - receivedAt;
}

/** The current time by the server's clock, in milliseconds. */
export function serverNow() {
  return Date.now() + offsetMs;
}

/**
 * The current time by the server's clock, renewed every `intervalMs`, for a page that has to follow
 * the time without new data, such as a tournament that starts while the page is open.
 */
export function useServerNow(intervalMs = 60_000) {
  const [now, setNow] = useState(serverNow);
  useInterval(() => setNow(serverNow()), intervalMs, { autoInvoke: true });
  return now;
}
