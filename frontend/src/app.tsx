import { useEffect, useMemo, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, Route, Routes, useLocation } from 'react-router';
import { Toaster } from 'sonner';

import { configureApiClient, fetchAuthFeatures, setUnauthorizedHandler } from './app/api';
import { showFlash, useSessionState } from './app/hooks';
import { LoginPage, PasswordResetStatusPage, RegisterPage } from './app/pages/auth-pages';
import { ClubsPage } from './app/pages/clubs-page';
import { HomePage } from './app/pages/home-page';
import { NotFoundPage, TournamentPage } from './app/pages/tournament-page';
import { UserPage } from './app/pages/user-page';
import { ErrorBoundary, TopNav } from './app/ui';

export function App() {
  const { session, setSession } = useSessionState();
  const queryClient = useQueryClient();
  const authFeatures = useQuery({
    queryKey: ['auth-features'],
    queryFn: fetchAuthFeatures,
  });
  const location = useLocation();

  // Configure the generated API client before child hooks fire requests.
  useMemo(() => configureApiClient(session), [session]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSession(null);
      showFlash({ text: 'Your session expired. Please log in again.', tone: 'error' });
    });
  }, [setSession]);

  // Only wipe cached data on logout. Clearing on mount would also drop the
  // anonymous queries that are already in flight, leaving them stuck pending.
  const hadSession = useRef(Boolean(session));
  useEffect(() => {
    if (hadSession.current && !session) queryClient.clear();
    hadSession.current = Boolean(session);
  }, [queryClient, session]);

  return (
    <div className="min-h-screen">
      <Toaster closeButton position="bottom-right" richColors theme="dark" />
      <TopNav
        authFeatures={authFeatures.data ?? null}
        currentUserName={session?.name ?? null}
        onLogout={() => {
          setSession(null);
          showFlash({ text: 'Logged out successfully.', tone: 'success' });
        }}
        session={session}
      />
      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-8 md:px-8 md:py-10">
        <ErrorBoundary key={location.pathname} title="This page failed to render">
          <Routes>
            <Route element={<HomePage session={session} setFlash={showFlash} />} path="/" />
            <Route
              element={
                <LoginPage
                  authFeatures={authFeatures.data ?? null}
                  setFlash={showFlash}
                  setSession={setSession}
                />
              }
              path="/login"
            />
            <Route
              element={
                <RegisterPage
                  authFeatures={authFeatures.data ?? null}
                  setFlash={showFlash}
                  setSession={setSession}
                />
              }
              path="/create-account"
            />
            <Route element={<PasswordResetStatusPage />} path="/password-reset" />
            <Route element={<ClubsPage session={session} setFlash={showFlash} />} path="/events" />
            <Route element={<UserPage session={session} setFlash={showFlash} />} path="/user" />

            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="overview"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="players"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/players"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="teams"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/teams"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="schedule"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/schedule"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="rankings"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/rankings"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="settings"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/settings"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="results"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/results"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="stages"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/stages"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode={false}
                  section="stages"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/stages/swiss/:stageItemId"
            />

            <Route
              element={
                <TournamentPage
                  dashboardMode
                  section="dashboard"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/dashboard"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode
                  section="dashboard-bracket"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/dashboard/bracket"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode
                  section="dashboard-standings"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/dashboard/standings"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode
                  section="dashboard-schedule"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/dashboard/present/schedule"
            />
            <Route
              element={<Navigate relative="path" replace to="../schedule" />}
              path="/tournaments/:tournamentKey/dashboard/present/courts"
            />
            <Route
              element={
                <TournamentPage
                  dashboardMode
                  section="dashboard-present-standings"
                  session={session}
                  setFlash={showFlash}
                />
              }
              path="/tournaments/:tournamentKey/dashboard/present/standings"
            />

            <Route element={<NotFoundPage />} path="*" />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
