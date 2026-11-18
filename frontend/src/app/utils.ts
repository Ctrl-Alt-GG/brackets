import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cx(...values: ClassValue[]) {
  return twMerge(clsx(values));
}

/** Groups items by a key, keeping the order in which the keys first appear. */
export function groupBy<T, K>(items: T[], key: (item: T) => K) {
  const groups = new Map<K, T[]>();
  for (const item of items) {
    const group = groups.get(key(item));
    if (group) group.push(item);
    else groups.set(key(item), [item]);
  }
  return groups;
}

export function sortTeamsByName<T extends { name: string }>(teams: T[]) {
  return teams.toSorted((left, right) => left.name.localeCompare(right.name));
}
