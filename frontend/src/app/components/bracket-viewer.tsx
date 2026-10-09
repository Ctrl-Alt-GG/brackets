import { lazy, Suspense, type ComponentProps } from 'react';

// brackets-viewer is a fifth of the app's code, so it only loads where a bracket is drawn.
const BracketViewerCanvas = lazy(() =>
  import('./bracket-viewer-canvas').then((module) => ({ default: module.BracketViewerCanvas })),
);

export function BracketViewer(props: ComponentProps<typeof BracketViewerCanvas>) {
  return (
    <Suspense fallback={<span className="loading loading-spinner" />}>
      <BracketViewerCanvas {...props} />
    </Suspense>
  );
}
