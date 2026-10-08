import { readLocalStorageValue, useLocalStorage } from '@mantine/hooks';

import type { Session } from './types';

const SESSION_KEY = 'bracket:session';

export function useSession() {
  return useLocalStorage<Session>({
    defaultValue: null,
    // Pages decide what to load from it in their first render.
    getInitialValueInEffect: false,
    key: SESSION_KEY,
  });
}

export function readSession() {
  return readLocalStorageValue<Session>({ defaultValue: null, key: SESSION_KEY });
}

/** The team a visitor picked as their own, remembered per tournament in this browser. */
export function useMyTeam(tournamentId: number) {
  return useLocalStorage<number | null>({
    defaultValue: null,
    getInitialValueInEffect: false,
    key: `bracket:my-team:${tournamentId}`,
  });
}
