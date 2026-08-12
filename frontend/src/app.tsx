import { useEffect } from 'react';
import { Route, Routes } from 'react-router';

import { configureApiClient, fetchAuthFeatures, setUnauthorizedHandler } from './app/api';
import { useActionFeedback, useResource, useSessionState } from './app/hooks';
import { LoginPage, PasswordResetStatusPage, RegisterPage } from './app/pages/auth-pages';
import { ClubsPage } from './app/pages/clubs-page';
import { HomePage } from './app/pages/home-page';
import { NotFoundPage, TournamentPage } from './app/pages/tournament-page';
import { UserPage } from './app/pages/user-page';
import { FlashBanner, TopNav } from './app/ui';

export function App() {
  const { message, setMessage } = useActionFeedback();
  const { session, setSession } = useSessionState();
  const authFeatures = useResource(() => fetchAuthFeatures(), []);

  // Configure the generated API client before child hooks fire requests.
  configureApiClient(session);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSession(null);
      setMessage({ text: 'Your session expired. Please log in again.', tone: 'error' });
    });
  }, []);

  return (
    <div className="min-h-screen">
      <TopNav
        authFeatures={authFeatures.data}
        currentUserName={session?.name ?? null}
        onLogout={() => {
          setSession(null);
          setMessage({ text: 'Logged out successfully.', tone: 'success' });
        }}
        session={session}
      />
      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-8 md:px-8 md:py-10">
        <FlashBanner message={message} />
        <Routes>
          <Route element={<HomePage session={session} setFlash={setMessage} />} path="/" />
          <Route
            element={
              <LoginPage
                authFeatures={authFeatures.data}
                setFlash={setMessage}
                setSession={setSession}
              />
            }
            path="/login"
          />
          <Route
            element={
              <RegisterPage
                authFeatures={authFeatures.data}
                setFlash={setMessage}
                setSession={setSession}
              />
            }
            path="/create-account"
          />
          <Route element={<PasswordResetStatusPage />} path="/password-reset" />
          <Route element={<ClubsPage session={session} setFlash={setMessage} />} path="/clubs" />
          <Route element={<UserPage session={session} setFlash={setMessage} />} path="/user" />

          <Route
            element={
              <TournamentPage
                dashboardMode={false}
                section="overview"
                session={session}
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
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
                setFlash={setMessage}
              />
            }
            path="/tournaments/:tournamentKey/dashboard"
          />
          <Route
            element={
              <TournamentPage
                dashboardMode
                section="dashboard-standings"
                session={session}
                setFlash={setMessage}
              />
            }
            path="/tournaments/:tournamentKey/dashboard/standings"
          />
          <Route
            element={
              <TournamentPage
                dashboardMode
                section="dashboard-courts"
                session={session}
                setFlash={setMessage}
              />
            }
            path="/tournaments/:tournamentKey/dashboard/present/courts"
          />
          <Route
            element={
              <TournamentPage
                dashboardMode
                section="dashboard-present-standings"
                session={session}
                setFlash={setMessage}
              />
            }
            path="/tournaments/:tournamentKey/dashboard/present/standings"
          />

          <Route element={<NotFoundPage />} path="*" />
        </Routes>
      </main>
    </div>
  );
}
