import { isAxiosError } from 'axios';

const FALLBACK = 'The request failed. Check your connection and try again.';

/** What went wrong with a request, in words an organizer can act on. */
export function getErrorMessage(error: unknown) {
  if (!isAxiosError<{ detail?: string | Array<{ loc: string[]; msg: string }> }>(error)) {
    return error instanceof Error && error.message ? error.message : FALLBACK;
  }

  const response = error.response;
  // Rate limits say how long to wait; the message follows that, whatever the answer's text.
  if (response?.status === 429) {
    const seconds = Number(response.headers?.['retry-after']);
    const minutes = Math.ceil(seconds / 60);
    return Number.isFinite(seconds) && seconds > 0
      ? `Too many attempts. Try again in ${minutes === 1 ? 'a minute' : `${minutes} minutes`}.`
      : 'Too many attempts. Try again in a few minutes.';
  }

  const detail = response?.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // "Value error, " is how the API prefixes the message of its own checks.
    return detail[0].msg.replace(/^Value error, /, '');
  }
  if (typeof detail === 'string' && detail) return detail;

  // A change can still have been saved when its answer didn't arrive in time.
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return 'The server took too long to answer. Reload to see what was saved.';
  }

  return error.message || FALLBACK;
}
