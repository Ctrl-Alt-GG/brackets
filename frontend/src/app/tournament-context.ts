import { createContext, useContext } from 'react';

export type TournamentContextValue = {
  /** Screens at the venue are read from afar: team names are not links there. */
  isBigScreen: boolean;
  myTeamId: number | null;
  /** Where the tournament's Details pages live, such as `/tournaments/summer-cup/dashboard`. */
  publicPath: string;
  setMyTeamId: (teamId: number | null) => void;
};

export const TournamentContext = createContext<TournamentContextValue | null>(null);

export function useTournamentContext() {
  const value = useContext(TournamentContext);
  if (value == null) throw new Error('Tournament pages must render inside TournamentContext.');
  return value;
}

export function teamPath(publicPath: string, teamId: number) {
  return `${publicPath}/teams/${teamId}`;
}
