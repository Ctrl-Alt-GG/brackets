import * as OpenApi from '../openapi';
import type { BracketViewerData, RoundNameInfo } from './bracket-adapter';

declare global {
  interface Window {
    __BRACKET_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
    };
    bracketsViewer?: {
      /** Adds or extends the labels of a language that the viewer writes itself. */
      addLocale: (name: string, locale: Record<string, unknown>) => Promise<void>;
      render: (
        data: BracketViewerData,
        config: {
          clear?: boolean;
          customRoundName?: (info: RoundNameInfo) => string;
          highlightParticipantOnHover?: boolean;
          selector?: string;
          showRankingTable?: boolean;
        },
      ) => Promise<void>;
    };
  }
}

/** Who is signed in. The session itself is an HttpOnly cookie, which the page can't read. */
export type Session =
  | (Pick<OpenApi.Token, 'name' | 'user_id'> & {
      /** When this browser signed in, which tells its requests apart from an earlier session's. */
      started?: number;
    })
  | null;

export type TournamentSection =
  // The workspace, where organizers run the tournament.
  | 'overview'
  | 'players'
  | 'teams'
  | 'schedule'
  | 'rankings'
  | 'settings'
  | 'stages'
  // The Details pages, which everyone can follow.
  | 'dashboard'
  | 'dashboard-schedule'
  | 'dashboard-standings'
  | 'dashboard-bracket'
  | 'dashboard-teams'
  | 'dashboard-team'
  | 'dashboard-present-schedule'
  | 'dashboard-present-standings';

/** Everything a tournament page shows. The Details pages have no slot choices or previews. */
export type TournamentBundle = OpenApi.TournamentDetails & {
  canManage: boolean;
  /** The teams and places that a stage's slots can take, by stage id. */
  availableInputs: OpenApi.TournamentWorkspace['available_inputs'];
  /** Who would take each slot of the next stage if it started now, by stage item id. */
  nextStageRankings: OpenApi.TournamentWorkspace['next_stage_rankings'];
};

export type FlattenedMatch = {
  stage: OpenApi.StageWithStageItems;
  stageItem: OpenApi.StageItemWithRounds;
  round: OpenApi.RoundWithMatches;
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;
};
