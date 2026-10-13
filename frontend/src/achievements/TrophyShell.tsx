import type { ReactNode } from 'react';
import { BrandIcon, RoadmapIcon, SandboxIcon, EscalationIcon, AnalysisIcon, AchievementIcon, ProgressIcon, BellIcon } from './icons';

export interface TrophyPageProps { displayName: string; role: string; sandboxUrl: string }
export function TrophyShell({ children, profile }: { children: ReactNode; profile: TrophyPageProps }) {
  const initials = profile.displayName.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase();
  const inactive = [[RoadmapIcon, 'Roadmap'], [EscalationIcon, 'Карта эскалаций'], [AnalysisIcon, 'Анализ тикетов'], [ProgressIcon, 'Мой прогресс']] as const;
  return <div className="tp-trophy-room">
    <header className="tp-topbar">
      <div className="tp-brand"><span className="tp-brand-icon"><BrandIcon /></span><strong>timeweb<span>&gt;</span>cloud</strong><span className="tp-training-tag">TRAINING</span></div>
      <div className="tp-profile"><button type="button" className="tp-bell" aria-label="Уведомления пока недоступны" disabled><BellIcon /><i /></button><span className="tp-avatar">{initials}</span><span><strong>{profile.displayName}</strong><small>{profile.role}</small></span></div>
    </header>
    <div className="tp-workspace"><aside className="tp-sidebar"><nav aria-label="Навигация Training Platform">
      <a href="/roadmap/" aria-label="Roadmap"><RoadmapIcon /><span>Roadmap</span></a>
      <a href={profile.sandboxUrl} aria-label="Ticket Sandbox"><SandboxIcon /><span>Ticket Sandbox</span></a>
      {inactive.slice(1, 3).map(([Icon, label]) => <button type="button" disabled title="Раздел пока недоступен" key={label}><Icon /><span>{label}</span></button>)}
      <a href="/achievements/" aria-label="Достижения" aria-current="page"><AchievementIcon /><span>Достижения</span></a>
      <button type="button" disabled title="Раздел пока недоступен"><ProgressIcon /><span>Мой прогресс</span></button>
    </nav><footer><span>Trophy Room 3.0</span><span>L1 Pro</span></footer></aside>
    <main className="tp-canvas">{children}</main></div>
  </div>;
}
