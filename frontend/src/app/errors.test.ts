import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it } from 'vitest';

import { getErrorMessage } from './errors';

function response(status: number, data: unknown, headers: Record<string, string> = {}) {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError(
    `Request failed with status code ${status}`,
    AxiosError.ERR_BAD_RESPONSE,
    config,
    null,
    { config, data, headers, status, statusText: '' },
  );
}

describe('getErrorMessage', () => {
  it("shows the API's own message", () => {
    expect(getErrorMessage(response(400, { detail: 'A knockout match needs a winner.' }))).toBe(
      'A knockout match needs a winner.',
    );
  });

  it('shows a validation message without where it came from', () => {
    const detail = [{ loc: ['body', 'names'], msg: 'Value error, Enter at least one name' }];

    expect(getErrorMessage(response(422, { detail }))).toBe('Enter at least one name');
  });

  it('says when to try again after too many attempts', () => {
    const body = { error: 'Rate limit exceeded' };

    expect(getErrorMessage(response(429, body, { 'retry-after': '45' }))).toBe(
      'Too many attempts. Try again in a minute.',
    );
    expect(getErrorMessage(response(429, body, { 'retry-after': '700' }))).toBe(
      'Too many attempts. Try again in 12 minutes.',
    );
    expect(getErrorMessage(response(429, body))).toBe(
      'Too many attempts. Try again in a few minutes.',
    );
  });

  it('says when to try again, not why the attempt that hit the limit was refused', () => {
    const lockedOut = response(
      429,
      { detail: 'Incorrect email or password' },
      { 'retry-after': '300' },
    );

    expect(getErrorMessage(lockedOut)).toBe('Too many attempts. Try again in 5 minutes.');
  });

  it('says that a change can have been saved when its answer took too long', () => {
    const timedOut = new AxiosError('timeout of 30000ms exceeded', AxiosError.ECONNABORTED);

    expect(getErrorMessage(timedOut)).toBe(
      'The server took too long to answer. Reload to see what was saved.',
    );
  });

  it('falls back to the error itself, then to a general message', () => {
    expect(getErrorMessage(new Error('Network Error'))).toBe('Network Error');
    expect(getErrorMessage(null)).toBe('The request failed. Check your connection and try again.');
  });
});
