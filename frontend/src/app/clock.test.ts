import { describe, expect, it } from 'vitest';

import { serverNow, syncClock } from './clock';

describe('serverNow', () => {
  it("follows the server's clock rather than the device's", () => {
    const deviceNow = Date.now();
    // The server is ten minutes ahead. Its header has whole seconds.
    syncClock(new Date(deviceNow + 10 * 60_000).toUTCString(), deviceNow);

    expect(Math.abs(serverNow() - (Date.now() + 10 * 60_000))).toBeLessThan(1_500);

    syncClock(new Date(deviceNow).toUTCString(), deviceNow);
  });

  it('keeps the last offset when an answer has no date', () => {
    const before = serverNow();
    syncClock(undefined);

    expect(Math.abs(serverNow() - before)).toBeLessThan(1_500);
  });
});
