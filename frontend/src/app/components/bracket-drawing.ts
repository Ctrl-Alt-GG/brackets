import type { BracketViewerData } from '../bracket-adapter';

type Viewer = NonNullable<Window['bracketsViewer']>;
type DrawingConfig = Parameters<Viewer['render']>[1];

/**
 * brackets-viewer is one object for the whole page, which keeps its labels and what it is drawing
 * between the steps of a drawing. Its drawings take turns, in the order they were asked for, so
 * two brackets on a page can't mix up each other's labels or data.
 */
export function createBracketDrawer(getViewer: () => Viewer | undefined) {
  let turn: Promise<unknown> = Promise.resolve();

  /**
   * Draws `data` once the drawings asked for earlier are done. `isWanted` is asked before every
   * step: a bracket that was left or changed in the meantime isn't drawn, and the answer is
   * `false` then.
   */
  return function draw(
    data: BracketViewerData,
    labels: Parameters<Viewer['addLocale']>[1],
    config: DrawingConfig,
    isWanted: () => boolean,
  ) {
    const drawing = turn.then(async () => {
      const viewer = getViewer();
      if (!viewer) throw new Error('brackets-viewer did not load.');
      if (!isWanted()) return false;
      // The labels the viewer writes itself. It picks English, or French, its only other
      // language, by the browser's settings, so both get the page's labels.
      await Promise.all([viewer.addLocale('en', labels), viewer.addLocale('fr', labels)]);
      if (!isWanted()) return false;
      await viewer.render(data, config);
      return isWanted();
    });
    turn = drawing.catch(() => undefined);
    return drawing;
  };
}

export const drawBracket = createBracketDrawer(() => window.bracketsViewer);
