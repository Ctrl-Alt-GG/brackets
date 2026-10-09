import { lazy, Suspense, useEffect, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  createBrowserRouter,
  isRouteErrorResponse,
  Navigate,
  Outlet,
  ScrollRestoration,
  useLocation,
  useRouteError,
} from 'react-router';
import { Toaster, toast } from 'sonner';

import { setUnauthorizedHandler } from './app/api';
import { useSession } from './app/hooks';
import { HomePage } from './app/pages/home-page';
import { NotFoundPage, TournamentPage } from './app/pages/tournament-page';
import { queryClient } from './app/query-client';
import { logoutApiLogoutPostMutation } from './openapi/@tanstack/react-query.gen';
import type { TournamentSection } from './app/types';
import { ErrorState, LoadingState, TopNav } from './app/ui';
import { cx } from './app/utils';

// Visitors only need the tournament pages, so the account pages load when someone opens them.
const LoginPage = lazy(() =>
  import('./app/pages/auth-pages').then((module) => ({ default: module.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('./app/pages/auth-pages').then((module) => ({ default: module.RegisterPage })),
);
const PasswordResetStatusPage = lazy(() =>
  import('./app/pages/auth-pages').then((module) => ({
    default: module.PasswordResetStatusPage,
  })),
);
const ClubsPage = lazy(() =>
  import('./app/pages/clubs-page').then((module) => ({ default: module.ClubsPage })),
);
const UserPage = lazy(() =>
  import('./app/pages/user-page').then((module) => ({ default: module.UserPage })),
);

const TOURNAMENT_ROUTES: Array<[path: string, section: TournamentSection]> = [
  ['', 'overview'],
  ['/players', 'players'],
  ['/teams', 'teams'],
  ['/schedule', 'schedule'],
  ['/rankings', 'rankings'],
  ['/settings', 'settings'],
  ['/stages', 'stages'],
  ['/stages/swiss/:stageItemId', 'stages'],
  ['/dashboard', 'dashboard'],
  ['/dashboard/schedule', 'dashboard-schedule'],
  ['/dashboard/standings', 'dashboard-standings'],
  ['/dashboard/bracket', 'dashboard-bracket'],
  ['/dashboard/teams', 'dashboard-teams'],
  ['/dashboard/teams/:teamId', 'dashboard-team'],
  ['/dashboard/present/schedule', 'dashboard-present-schedule'],
  ['/dashboard/present/standings', 'dashboard-present-standings'],
];

function RootLayout() {
  const [session, setSession] = useSession();
  const location = useLocation();
  // A big screen at the venue shows the tournament only, without the site's navigation.
  const isBigScreen = location.pathname.includes('/dashboard/present/');
  // Only the API can remove the session cookie. This browser is signed out even if it fails.
  const logout = useMutation({
    ...logoutApiLogoutPostMutation(),
    meta: { invalidates: [], successMessage: 'Logged out successfully.' },
    onSettled: () => setSession(null),
  });

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSession(null);
      toast.error('Your session expired. Please log in again.');
    });
  }, [setSession]);

  // Only wipe cached data on logout. Clearing on mount would also drop the
  // anonymous queries that are already in flight, leaving them stuck pending.
  const hadSession = useRef(Boolean(session));
  useEffect(() => {
    if (hadSession.current && !session) queryClient.clear();
    hadSession.current = Boolean(session);
  }, [session]);

  return (
    <div className="min-h-screen">
      <Toaster closeButton position="bottom-right" richColors theme="dark" />
      {isBigScreen ? null : (
        <TopNav
          currentUserName={session?.name ?? null}
          onLogout={() => logout.mutate({})}
          session={session}
        />
      )}
      <main
        className={cx(
          'mx-auto flex flex-col gap-6 px-5 py-8 md:px-8 md:py-10',
          isBigScreen ? 'max-w-[110rem]' : 'max-w-7xl',
        )}
      >
        <Suspense fallback={<LoadingState title="Loading…" />}>
          <Outlet />
        </Suspense>
      </main>
      {/* Also scrolls to the element a link's hash names, such as a group in the standings. */}
      <ScrollRestoration />
    </div>
  );
}

function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? error.statusText
    : error instanceof Error
      ? error.message
      : 'An unexpected error occurred.';

  return (
    <ErrorState
      action={
        <button className="btn btn-sm" onClick={() => window.location.reload()} type="button">
          Reload the page
        </button>
      }
      error={message}
      title="This page failed to render"
    />
  );
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      {
        // Inside the layout, so a page that fails keeps the site's navigation.
        errorElement: <RouteError />,
        children: [
          { element: <HomePage />, path: '/' },
          { element: <LoginPage />, path: '/login' },
          { element: <RegisterPage />, path: '/create-account' },
          { element: <PasswordResetStatusPage />, path: '/password-reset' },
          { element: <ClubsPage />, path: '/events' },
          { element: <UserPage />, path: '/user' },
          ...TOURNAMENT_ROUTES.map(([path, section]) => ({
            element: <TournamentPage section={section} />,
            path: `/tournaments/:tournamentKey${path}`,
          })),
          // Finished matches are part of the schedule now.
          {
            element: <Navigate relative="path" replace to="../schedule" />,
            path: '/tournaments/:tournamentKey/results',
          },
          {
            element: <Navigate relative="path" replace to="../schedule" />,
            path: '/tournaments/:tournamentKey/dashboard/present/courts',
          },
          { element: <NotFoundPage />, path: '*' },
        ],
      },
    ],
  },
]);
