export type Metal = 'bronze' | 'silver' | 'gold' | 'platinum';
export type StatusFilter = 'all' | 'earned' | 'locked' | 'secret';
export type MetalFilter = 'all' | Metal;
export type MedalArt = 'MissionArt' | 'ArchitectureArt' | 'AutomationArt' | 'MilestoneArt' | 'SyncArt' | 'GuardianArt' | 'MasterArt' | 'SecretProtocolArt' | 'SecretFrontierArt';
export interface Tier { code: string; rank: number; rarity: Metal; criterion?: string; automatic?: boolean }
export interface Progress { percent: number; label: string; summary?: string }
export interface Achievement {
  id: string; title: string; description: string | null;
  status: 'earned' | 'locked' | 'revoked'; applicable: boolean | null; secret: boolean; revealed: boolean;
  highestTier: Tier | null; supportedTiers: readonly Tier[]; category: string | null; artKey: string;
  progress: Progress | null; earnedAt: string | null; lastUpgradedAt: string | null;
  manualGrant: boolean; dataQuality: string; revision: number;
}
export interface TrophyStats { earned: number; applicable_total: number; rarities: Record<Metal, number> }
export interface TrophyCollection { items: readonly Achievement[]; stats: TrophyStats; pendingEvents: number }
export interface AchievementEvent {
  id: number; action: 'grant' | 'upgrade' | 'revoke' | 'evidence_disputed';
  from_tier: string | null; to_tier: string | null; occurred_at: string; recorded_at: string;
  source: string; manual: boolean; actor_id: number | null; reason: string; rule_version: number;
}
export interface TrophyDetail { achievement: Achievement; history: readonly AchievementEvent[]; nextCursor: number | null }
export const metalLabels: Record<Metal, string> = { bronze: 'Бронза', silver: 'Серебро', gold: 'Золото', platinum: 'Платина' };
export function isHidden(a: Achievement): boolean { return a.secret && !a.revealed; }
export function displayTitle(a: Achievement): string { return isHidden(a) ? 'Секретное достижение' : a.title; }
export function displayMetal(a: Achievement): Metal | null {
  if (isHidden(a)) return null;
  return a.highestTier?.rarity ?? (a.supportedTiers.length === 1 ? a.supportedTiers[0].rarity : null);
}
export function matchesFilters(a: Achievement, status: StatusFilter, metal: MetalFilter, category = 'all'): boolean {
  const statusMatch = status === 'all' || (status === 'secret' ? a.secret : status === 'earned' ? a.status === 'earned' : a.status !== 'earned');
  return statusMatch && (metal === 'all' || displayMetal(a) === metal) && (category === 'all' || (!isHidden(a) && a.category === category));
}
export function formatDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}
export function conditionLabel(value: string | undefined): string | undefined {
  return value?.replace(/OPTIONAL_REVIEW\s*→\s*NO_REVIEW/g, 'от проверок по желанию к работе без проверок')
    .replaceAll('WITH_REVIEW', 'с обязательными проверками').replaceAll('NO_REVIEW', 'этапе без проверок');
}
export function cardStatus(a: Achievement): string {
  if (isHidden(a)) return 'Засекречено';
  if (a.status === 'earned') return formatDate(a.earnedAt) ? `Получено ${formatDate(a.earnedAt)}` : 'Получено';
  if (a.applicable === false) return 'Не требуется';
  if (a.status === 'revoked') return 'Отозвано';
  if (a.applicable === null) return 'Применимость уточняется';
  return 'Не получено';
}
// Static illustrations are isolated to the explicit staff demonstration.
export interface DemoAchievement {
  id: string; title: string; description: string; metal: Metal; status: 'earned' | 'locked';
  progress: Progress; condition: string; earnedAt: string | null; secret: boolean;
  manualGrant: boolean; mentorComment: { text: string; author: string } | null; art: MedalArt;
}
