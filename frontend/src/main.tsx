import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';
import { QueryClientProvider } from '@tanstack/react-query';

import { router } from './app';
import { queryClient } from './app/query-client';
import './styles.css';

// The deployed app has shown intermittent blank first paints; log anything that escapes React.
window.addEventListener('error', (event) => {
  console.error('[bracket] uncaught error', event.error ?? event.message);
});
window.addEventListener('unhandledrejection', (event) => {
  console.error('[bracket] unhandled rejection', event.reason);
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
