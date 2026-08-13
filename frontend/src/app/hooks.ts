import { useCallback, useEffect, useState } from 'react';

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

export function useActionFeedback() {
  const [message, setMessage] = useState<FlashMessage>(null);

  useEffect(() => {
    if (!message) return;
    const timeout = window.setTimeout(() => setMessage(null), 5_000);
    return () => window.clearTimeout(timeout);
  }, [message]);

  return { message, setMessage };
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
