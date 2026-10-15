import { demoAchievements } from './data';
import type { Achievement } from './types';

export function demoCollection() {
  const items: Achievement[] = demoAchievements.map(a => ({
    id: `demo-${a.id}`, title: a.title, description: a.description, status: a.status,
    applicable: true, secret: a.secret, revealed: !a.secret || a.status === 'earned',
    highestTier: a.status === 'earned' ? { code: a.metal, rank: 1, rarity: a.metal } : null,
    supportedTiers: [{ code: a.metal, rank: 1, rarity: a.metal, criterion: a.condition }],
    category: 'Демонстрация', artKey: a.art, progress: a.progress,
    earnedAt: null, lastUpgradedAt: null, manualGrant: a.manualGrant, dataQuality: 'demo', revision: 0,
  }));
  return { items, pendingEvents: 0, stats: demoStats(items) };
}
export function demoStats(items: readonly Achievement[]) {
  const earned = items.filter(a => a.status === 'earned');
  return { earned: earned.length, applicable_total: items.length, rarities: {
    bronze: earned.filter(a => a.highestTier?.rarity === 'bronze').length,
    silver: earned.filter(a => a.highestTier?.rarity === 'silver').length,
    gold: earned.filter(a => a.highestTier?.rarity === 'gold').length,
    platinum: earned.filter(a => a.highestTier?.rarity === 'platinum').length,
  } };
}
export function demoUnlock(items: readonly Achievement[], canDemo: boolean): readonly Achievement[] {
  if (!canDemo) return items;
  return items.map(a => a.id === 'demo-3' ? { ...a, status: 'earned', highestTier: a.supportedTiers[0],
    progress: { percent: 100, label: 'Демонстрация завершения' } } : a);
}
