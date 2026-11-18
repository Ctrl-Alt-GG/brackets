import { describe, expect, it } from 'vitest';

import { tournament } from './test-fixtures';
import {
  loginPath,
  publicTournamentPath,
  safeNextPath,
  teamLogoUrl,
  tournamentLogoUrl,
} from './urls';

describe('loginPath and safeNextPath', () => {
  it('brings the organizer back to the page they came from', () => {
    expect(loginPath('/tournaments/3/stages')).toBe('/login?next=%2Ftournaments%2F3%2Fstages');
  });

  it('has nowhere to return to from the home page or the account pages', () => {
    expect(loginPath('/')).toBe('/login');
    expect(loginPath('/login')).toBe('/login');
    expect(loginPath('/create-account')).toBe('/login');
  });

  it('only follows a path on this site', () => {
    expect(safeNextPath('/tournaments/3/stages')).toBe('/tournaments/3/stages');
    expect(safeNextPath(null)).toBe('/');
    expect(safeNextPath('https://evil.example/')).toBe('/');
    expect(safeNextPath('//evil.example/')).toBe('/');
    expect(safeNextPath('/\\evil.example/')).toBe('/');
    expect(safeNextPath('javascript:alert(1)')).toBe('/');
  });
});

describe('links', () => {
  it('uses the Details link only while the Details page is on', () => {
    const named = { dashboard_endpoint: ' summer-cup ' };

    expect(publicTournamentPath(tournament({ ...named, dashboard_public: true }))).toBe(
      '/tournaments/summer-cup/dashboard',
    );
    expect(publicTournamentPath(tournament(named))).toBe('/tournaments/7/dashboard');
    expect(publicTournamentPath(tournament({ dashboard_public: true }))).toBe(
      '/tournaments/7/dashboard',
    );
  });

  it('has no logo address without a logo', () => {
    expect(tournamentLogoUrl(tournament())).toBeNull();
    expect(teamLogoUrl({ id: 4, logo_path: null, tournament_id: 7 })).toBeNull();
  });

  it('changes the logo address with every upload, so browsers fetch the new picture', () => {
    expect(tournamentLogoUrl(tournament({ logo_path: 'a b.png' }))).toBe(
      '/api/tournaments/7/logo?v=a%20b.png',
    );
    expect(teamLogoUrl({ id: 4, logo_path: 'new.jpg', tournament_id: 7 })).toBe(
      '/api/tournaments/7/teams/4/logo?v=new.jpg',
    );
  });
});
