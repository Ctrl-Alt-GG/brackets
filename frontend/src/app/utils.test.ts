import { describe, expect, it } from 'vitest';

import { groupBy } from './utils';

describe('groupBy', () => {
  it('keeps the groups and their items in the order they appear', () => {
    const groups = groupBy(['b1', 'a1', 'b2', 'c1', 'a2'], (item) => item[0]);

    expect([...groups]).toEqual([
      ['b', ['b1', 'b2']],
      ['a', ['a1', 'a2']],
      ['c', ['c1']],
    ]);
  });
});
