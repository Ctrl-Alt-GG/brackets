import * as OpenApi from '../openapi';

export function isNumericIdentifier(value: string) {
  return /^\d+$/.test(value);
}

/**
 * The API's origin, which requests add `/api/...` to. The container's entrypoint checks the
 * configured one and writes it to `/runtime-config.js`. Without one, as behind the Vite dev
 * server's proxy, the API is on the page's own origin.
 */
export function getApiBaseUrl() {
  return (typeof window !== 'undefined' && window.__BRACKET_RUNTIME_CONFIG__?.apiBaseUrl) || '';
}

/**
 * Where an uploaded logo is served. The file name changes with every upload, so adding it makes
 * browsers fetch the new picture instead of showing the one they kept.
 */
export function tournamentLogoUrl(tournament: OpenApi.Tournament) {
  if (!tournament.logo_path) return null;
  const version = encodeURIComponent(tournament.logo_path);
  return `${getApiBaseUrl()}/api/tournaments/${tournament.id}/logo?v=${version}`;
}

/** A team's logo, which is the same in every tournament the team plays in. */
export function teamLogoUrl(team: { id: number; logo_path: string | null }) {
  if (!team.logo_path) return null;
  const version = encodeURIComponent(team.logo_path);
  return `${getApiBaseUrl()}/api/teams/${team.id}/logo?v=${version}`;
}

/** The login page, which brings the organizer back to `from` once they are signed in. */
export function loginPath(from: string) {
  const isWorthReturningTo = from !== '/' && !/^\/(login|create-account)\b/.test(from);
  return isWorthReturningTo ? `/login?next=${encodeURIComponent(from)}` : '/login';
}

/** Only a path of this site: `next` is in the address bar, where anyone can put anything. */
export function safeNextPath(next: string | null) {
  return next != null && /^\/(?![/\\])/.test(next) ? next : '/';
}

export function normalizeDashboardEndpoint(value: unknown) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/**
 * The tournament's Details page. Its custom link only resolves while the page is enabled, and the
 * tournament id always does.
 */
export function publicTournamentPath(tournament: OpenApi.Tournament) {
  const endpoint = tournament.dashboard_public
    ? normalizeDashboardEndpoint(tournament.dashboard_endpoint)
    : null;
  return `/tournaments/${endpoint ?? tournament.id}/dashboard`;
}
