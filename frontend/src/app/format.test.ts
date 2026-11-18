import { describe, expect, it } from 'vitest';

import { formatPoints } from './format';

describe('formatPoints', () => {
  it('shows every decimal place that the API keeps, without trailing zeros', () => {
    expect(formatPoints('3.000000')).toBe('3');
    expect(formatPoints('2.500000')).toBe('2.5');
    expect(formatPoints('0.000001')).toBe('0.000001');
    expect(formatPoints('-1.000001')).toBe('-1.000001');
  });

  it('keeps points apart that differ below a hundredth, as the standings rank them', () => {
    expect(formatPoints('3.001')).not.toBe(formatPoints('3.004'));
  });
});
