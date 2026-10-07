import { matchQuery, MutationCache, QueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import { getErrorMessage } from './utils';

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /** The queries to refresh afterwards, matched by key prefix. Without it, all of them. */
      invalidates?: QueryKey[];
      /** Shown once the change is saved and the page already shows the new data. */
      successMessage?: string;
    };
  }
}

export const queryClient: QueryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
  // A change can show up on any page, so by default every query is refreshed after it. Returning
  // the promise keeps the mutation pending until the new data is in.
  mutationCache: new MutationCache({
    onError: (error) => {
      toast.error(getErrorMessage(error));
    },
    onSuccess: async (_data, _variables, _context, mutation) => {
      const { invalidates } = mutation.meta ?? {};
      await queryClient.invalidateQueries({
        predicate: (query) =>
          invalidates?.some((queryKey) => matchQuery({ queryKey }, query)) ?? true,
      });
      if (mutation.meta?.successMessage) toast.success(mutation.meta.successMessage);
    },
  }),
});
