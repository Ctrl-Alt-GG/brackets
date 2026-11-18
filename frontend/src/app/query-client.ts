import { matchQuery, MutationCache, QueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getAuthFeaturesApiAuthFeaturesGetQueryKey,
  getUserApiUsersMeGetQueryKey,
} from '../openapi/@tanstack/react-query.gen';
import { getErrorMessage } from './errors';

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /**
       * The queries that the change makes out of date, matched by key prefix. Without it, all of
       * them except who is signed in and what the server offers, which only the account pages
       * change, and which they name.
       */
      invalidates?: QueryKey[];
      /** Shown once the server has saved the change. */
      successMessage?: string;
    };
  }
}

function matchesAny(queryKeys: QueryKey[]) {
  return (query: Parameters<typeof matchQuery>[1]) =>
    queryKeys.some((queryKey) => matchQuery({ queryKey }, query));
}

export const queryClient: QueryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
  // A change can show up on any page, so by default every query is refreshed after it. The change
  // is done once the server has saved it; the refresh follows in the background. A page whose
  // refresh fails keeps its data and says that it may be out of date.
  mutationCache: new MutationCache({
    onError: (error) => {
      toast.error(getErrorMessage(error));
    },
    onSuccess: (_data, _variables, _context, mutation) => {
      const { invalidates, successMessage } = mutation.meta ?? {};
      if (successMessage) toast.success(successMessage);
      const unaffected = matchesAny([
        getUserApiUsersMeGetQueryKey(),
        getAuthFeaturesApiAuthFeaturesGetQueryKey(),
      ]);
      void queryClient.invalidateQueries({
        predicate: invalidates ? matchesAny(invalidates) : (query) => !unaffected(query),
      });
    },
  }),
});
