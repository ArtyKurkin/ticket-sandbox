export type Metal = 'bronze' | 'silver' | 'gold' | 'platinum';
export type StatusFilter = 'all' | 'earned' | 'locked' | 'secret';
export type MetalFilter = 'all' | Metal;
export type MedalArt = 'MissionArt' | 'ArchitectureArt' | 'AutomationArt' | 'MilestoneArt' | 'SyncArt' | 'GuardianArt' | 'MasterArt' | 'SecretProtocolArt' | 'SecretFrontierArt';

export interface Achievement {
  id: string;
  title: string;
  description: string;
  metal: Metal;
  status: 'earned' | 'locked';
  progress: { percent: number; label: string; summary?: string };
  condition: string;
  earnedAt: string | null;
  secret: boolean;
  manualGrant: boolean;
  mentorComment: { text: string; author: string } | null;
  art: MedalArt;
}

export const metalLabels: Record<Metal, string> = {
  bronze: 'Бронза', silver: 'Серебро', gold: 'Золото', platinum: 'Платина',
};
export function isHidden(achievement: Achievement): boolean {
  return achievement.secret && achievement.status !== 'earned';
}
export function displayTitle(achievement: Achievement): string {
  return isHidden(achievement) ? 'Секретное достижение' : achievement.title;
}
export function matchesFilters(achievement: Achievement, status: StatusFilter, metal: MetalFilter): boolean {
  const statusMatch = status === 'all' || (status === 'secret' ? achievement.secret :
    status === 'locked' ? achievement.status === 'locked' && !achievement.secret : achievement.status === 'earned');
  return statusMatch && (metal === 'all' || achievement.metal === metal);
}
