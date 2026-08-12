import * as OpenApi from '../openapi';

declare global {
  interface Window {
    __BRACKET_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

export type Session = (OpenApi.Token & { name?: string }) | null;
export type FlashTone = 'success' | 'error';
export type FlashMessage = { tone: FlashTone; text: string } | null;
export type AuthFeatures = {
  passwordResetEnabled: boolean;
  userRegistrationEnabled: boolean;
};
export type TournamentSection =
  | 'overview'
  | 'players'
  | 'teams'
  | 'schedule'
  | 'rankings'
  | 'settings'
  | 'results'
  | 'stages'
  | 'dashboard'
  | 'dashboard-standings'
  | 'dashboard-courts'
  | 'dashboard-present-standings';

export type UpcomingSuggestion = {
  stageId: number;
  stageItemId: number;
  stageName: string;
  stageItemName: string;
  suggestion: OpenApi.SuggestedMatch;
};

export type TournamentBundle = {
  canManage: boolean;
  tournament: OpenApi.Tournament;
  stages: OpenApi.StageWithStageItems[];
  players: OpenApi.Player[];
  teams: OpenApi.FullTeamWithPlayers[];
  rankings: OpenApi.Ranking[];
  courts: OpenApi.Court[];
  availableInputs: Record<
    string,
    Array<OpenApi.StageItemInputOptionFinal | OpenApi.StageItemInputOptionTentative>
  >;
  nextStageRankings: Record<string, OpenApi.StageItemInputUpdate[]>;
  upcomingMatches: UpcomingSuggestion[];
};

export type FlattenedMatch = {
  stage: OpenApi.StageWithStageItems;
  stageItem: OpenApi.StageItemWithRounds;
  round: OpenApi.RoundWithMatches;
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;
};
