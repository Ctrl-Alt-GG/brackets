import { isAxiosError } from 'axios';
import { getI18n } from 'react-i18next';

/**
 * What went wrong with a request, in words an organizer can act on, in the page's language. The
 * API writes its own messages in the language the page asks for.
 */
export function getErrorMessage(error: unknown) {
  const { t } = getI18n();
  if (!isAxiosError<{ detail?: string | Array<{ loc: string[]; msg: string }> }>(error)) {
    return error instanceof Error && error.message ? error.message : t('errors.requestFailed');
  }

  const response = error.response;
  // Rate limits say how long to wait; the message follows that, whatever the answer's text.
  if (response?.status === 429) {
    const seconds = Number(response.headers?.['retry-after']);
    return Number.isFinite(seconds) && seconds > 0
      ? t('errors.tooManyAttemptsIn', { count: Math.ceil(seconds / 60) })
      : t('errors.tooManyAttempts');
  }

  const detail = response?.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // "Value error, " is how the API prefixes the message of its own checks.
    return detail[0].msg.replace(/^Value error, /, '');
  }
  if (typeof detail === 'string' && detail) return detail;

  // A change can still have been saved when its answer didn't arrive in time.
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return t('errors.timeout');
  }

  // Axios's own message, such as "Network Error", is in English.
  return t('errors.requestFailed');
}
