import type { Achievement } from './types';
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

export function TrophyMedallion({ achievement }: { achievement: Achievement }) {
  const Art = art[achievement.art];
  return <span className="tp-medallion-stage"><Art />{achievement.status === 'locked' &&
    <span className="tp-medallion-lock" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="6" y="10" width="12" height="11" rx="2" /><path d="M9 10V6a3 3 0 0 1 6 0v4M12 14v3" /></svg></span>}</span>;
}
