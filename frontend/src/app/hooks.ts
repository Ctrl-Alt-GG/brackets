import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { TOURNAMENT_BUNDLE_QUERY_KEY } from './api';
import type { FlashMessage, Session } from './types';
import { getErrorMessage, readSession, writeSession } from './utils';

export function useResource<T>(
  loader: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
  enabled = true,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshIndex, setRefreshIndex] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    loader()
      .then((value) => {
        if (cancelled) return;
        setData(value);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(getErrorMessage(reason));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, refreshIndex, ...deps]);

  return {
    data,
    error,
    loading,
    refresh: () => setRefreshIndex((value) => value + 1),
  };
}

export function useSessionState() {
  const [session, setSession] = useState<Session>(() => readSession());

  const updateSession = useCallback((nextSession: Session) => {
    writeSession(nextSession);
    setSession(nextSession);
  }, []);

  return { session, setSession: updateSession };
}

export function showFlash(message: FlashMessage) {
  if (!message) return;
  if (message.tone === 'error') toast.error(message.text);
  else toast.success(message.text);
}

/**
 * A change to the tournament: errors are reported, and on success the tournament is reloaded
 * before the success message shows, so `isPending` covers the whole round trip.
 */
export function useTournamentMutation<TVariables = void>(
  mutationFn: (variables: TVariables) => Promise<unknown>,
  successMessage: string | ((variables: TVariables) => string),
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onError: (error) => toast.error(getErrorMessage(error)),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: TOURNAMENT_BUNDLE_QUERY_KEY });
      toast.success(
        typeof successMessage === 'function' ? successMessage(variables) : successMessage,
      );
    },
  });
}

export async function runAction(
  setFlash: (message: FlashMessage) => void,
  action: () => Promise<void>,
  successText: string,
  onSuccess?: () => void,
) {
  try {
    await action();
    setFlash({ text: successText, tone: 'success' });
    onSuccess?.();
    return true;
  } catch (error) {
    setFlash({ text: getErrorMessage(error), tone: 'error' });
    return false;
  }
}
