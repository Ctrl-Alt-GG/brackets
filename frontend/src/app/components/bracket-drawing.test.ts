import { describe, expect, it, vi } from 'vitest';

import type { BracketViewerData } from '../bracket-adapter';
import { createBracketDrawer } from './bracket-drawing';

function bracket(name: string) {
  return { stages: [{ name }] } as unknown as BracketViewerData;
}

/** A viewer whose labels arrive when the test lets them. */
function slowViewer() {
  const pending: Array<() => void> = [];
  const viewer = {
    addLocale: vi.fn<(name: string, labels: object) => Promise<void>>(
      () => new Promise<void>((resolve) => pending.push(resolve)),
    ),
    render: vi.fn<(data: BracketViewerData) => Promise<void>>(async () => undefined),
  };
  return {
    /** Waits until a drawing asks the viewer for its labels. */
    labelsAsked: () => vi.waitFor(() => expect(pending.length).toBeGreaterThan(0)),
    /** Lets the labels that were asked for arrive. */
    labelsArrive: () => {
      for (const resolve of pending.splice(0)) resolve();
    },
    viewer,
  };
}

const config = { selector: '#bracket' };

describe('drawBracket', () => {
  it("doesn't draw a bracket that was left while its labels were on the way", async () => {
    const { labelsArrive, labelsAsked, viewer } = slowViewer();
    const draw = createBracketDrawer(() => viewer);
    let wanted = true;

    const drawing = draw(bracket('left'), {}, config, () => wanted);
    await labelsAsked();
    wanted = false;
    labelsArrive();

    await expect(drawing).resolves.toBe(false);
    expect(viewer.render).not.toHaveBeenCalled();
  });

  it('draws one bracket at a time, so a newer drawing never comes before an older one', async () => {
    const { labelsArrive, labelsAsked, viewer } = slowViewer();
    const draw = createBracketDrawer(() => viewer);

    const older = draw(bracket('older'), {}, config, () => true);
    const newer = draw(bracket('newer'), {}, config, () => true);
    await labelsAsked();
    // Only the older drawing's labels, in English and French: the newer one waits.
    expect(viewer.addLocale).toHaveBeenCalledTimes(2);
    labelsArrive();
    await older;
    await labelsAsked();
    labelsArrive();
    await newer;

    expect(viewer.render.mock.calls.map(([data]) => data)).toEqual([
      bracket('older'),
      bracket('newer'),
    ]);
  });

  it('skips a drawing that a newer one replaced while it waited for its turn', async () => {
    const { labelsArrive, labelsAsked, viewer } = slowViewer();
    const draw = createBracketDrawer(() => viewer);
    let replacedWanted = true;

    const first = draw(bracket('first'), {}, config, () => true);
    const replaced = draw(bracket('replaced'), {}, config, () => replacedWanted);
    replacedWanted = false;
    const newer = draw(bracket('newer'), {}, config, () => true);
    await labelsAsked();
    labelsArrive();
    await first;
    await expect(replaced).resolves.toBe(false);
    await labelsAsked();
    labelsArrive();
    await expect(newer).resolves.toBe(true);

    expect(viewer.render.mock.calls.map(([data]) => data)).toEqual([
      bracket('first'),
      bracket('newer'),
    ]);
  });

  it('reports a drawing that failed, and still draws the next one', async () => {
    const viewer = {
      addLocale: vi.fn<(name: string, labels: object) => Promise<void>>(async () => undefined),
      render: vi
        .fn<(data: BracketViewerData) => Promise<void>>()
        .mockRejectedValueOnce(new Error('Root not found'))
        .mockResolvedValue(undefined),
    };
    const draw = createBracketDrawer(() => viewer);

    await expect(draw(bracket('broken'), {}, config, () => true)).rejects.toThrow('Root not found');
    await expect(draw(bracket('next'), {}, config, () => true)).resolves.toBe(true);
  });

  it('fails without the viewer, which loads with the page', async () => {
    const draw = createBracketDrawer(() => undefined);

    await expect(draw(bracket('any'), {}, config, () => true)).rejects.toThrow(
      'brackets-viewer did not load.',
    );
  });
});
