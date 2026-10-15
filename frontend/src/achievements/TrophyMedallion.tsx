import type { Achievement } from './types';
import { displayMetal, isHidden } from './types';
import { paletteStyle } from './palette';
import { MissionArt } from './art/MissionArt';
import { ArchitectureArt } from './art/ArchitectureArt';
import { AutomationArt } from './art/AutomationArt';
import { MilestoneArt } from './art/MilestoneArt';
import { SyncArt } from './art/SyncArt';
import { GuardianArt } from './art/GuardianArt';
import { MasterArt } from './art/MasterArt';
import { SecretProtocolArt } from './art/SecretProtocolArt';
import { SecretFrontierArt } from './art/SecretFrontierArt';
const art = { MissionArt, ArchitectureArt, AutomationArt, MilestoneArt, SyncArt, GuardianArt, MasterArt, SecretProtocolArt, SecretFrontierArt };
const registry: Record<string, keyof typeof art> = {
  generic: 'MissionArt', training: 'MissionArt', sandbox: 'MilestoneArt', quality: 'ArchitectureArt',
  speed: 'AutomationArt', probation: 'MasterArt', milestone: 'MilestoneArt', independent: 'SyncArt',
};

export function TrophyMedallion({ achievement }: { achievement: Achievement }) {
  const hidden = isHidden(achievement);
  const key = hidden ? 'SecretProtocolArt' : achievement.dataQuality === 'demo' && Object.hasOwn(art, achievement.artKey)
    ? achievement.artKey as keyof typeof art : Object.hasOwn(registry, achievement.artKey) ? registry[achievement.artKey] : 'MissionArt';
  const Art = art[key];
  const metal = hidden ? null : displayMetal(achievement);
  return <span className="tp-medallion-stage" style={paletteStyle(metal)} data-palette={metal ?? 'neutral'}><Art />{achievement.status !== 'earned' &&
    <span className="tp-medallion-lock" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="6" y="10" width="12" height="11" rx="2" /><path d="M9 10V6a3 3 0 0 1 6 0v4M12 14v3" /></svg></span>}</span>;
}
