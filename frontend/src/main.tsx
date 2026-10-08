import './zod-config';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';
import { QueryClientProvider } from '@tanstack/react-query';
// Self-hosted, so pages load no third-party resources (see the Content-Security-Policy).
import '@fontsource-variable/outfit';
import '@fontsource-variable/sora';

import { router } from './app';
import { configureApiClient } from './app/api';
import { queryClient } from './app/query-client';
import './styles.css';

configureApiClient();

// Sessions used to keep their token in localStorage. It is an HttpOnly cookie now, so a copy left
// over from an earlier visit is removed.
try {
  window.localStorage.removeItem('login');
} catch {
  // Storage can be unavailable, as in some private windows.
}

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
