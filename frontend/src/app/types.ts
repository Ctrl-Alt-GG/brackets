import * as OpenApi from '../openapi';
import type { BracketViewerData, RoundNameInfo } from './bracket-adapter';

declare global {
  interface Window {
    __BRACKET_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
    };
    bracketsViewer?: {
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
export type Session = Pick<OpenApi.Token, 'name' | 'user_id'> | null;

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

export type TournamentBundle = {
  canManage: boolean;
  tournament: OpenApi.Tournament;
  stages: OpenApi.StageWithStageItems[];
  players: OpenApi.Player[];
  teams: OpenApi.FullTeamWithPlayers[];
  rankings: OpenApi.Ranking[];
  /** The ranked inputs of every stage item by stage item id, best first. */
  standings: Record<string, OpenApi.StageItemInputStanding[]>;
  availableInputs: Record<
    string,
    Array<OpenApi.StageItemInputOptionFinal | OpenApi.StageItemInputOptionTentative>
  >;
  nextStageRankings: Record<string, OpenApi.StageItemInputUpdate[]>;
};

export type FlattenedMatch = {
  stage: OpenApi.StageWithStageItems;
  stageItem: OpenApi.StageItemWithRounds;
  round: OpenApi.RoundWithMatches;
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;
};
