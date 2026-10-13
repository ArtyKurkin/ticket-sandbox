import { useState, type ReactNode } from 'react';
import type { RoadmapProps } from './types';
import { BrandIcon, MapIcon, TicketIcon, EscalationIcon, AnalysisIcon, MedalIcon, ProgressIcon, BellIcon } from './icons';
export function RoadmapShell({ children, profile }: { children: ReactNode; profile: RoadmapProps }) {
  const [parallax, setParallax] = useState({ x: 0, y: 0 });
  const initials = profile.displayName.split(/\s+/).filter(Boolean).slice(0,2).map(value=>value[0]).join('').toUpperCase();
  return <div className="rm-page">
    <header className="rm-topbar"><div className="rm-brand"><span className="rm-logo"><BrandIcon /></span><strong>timeweb<span>&gt;</span>cloud</strong><span className="rm-training-tag">TRAINING</span></div>
      <div className="rm-profile"><span className="rm-bell" aria-hidden="true"><BellIcon /><i /></span><span className="rm-avatar">{initials}</span><span><strong>{profile.displayName}</strong><small>{profile.role}</small></span></div></header>
    <div className="rm-workspace"><aside className="rm-sidebar"><nav aria-label="Навигация Training Platform">
      <a href="/roadmap/" aria-label="Roadmap" aria-current="page"><MapIcon /><span>Roadmap</span></a>
      <a href={profile.sandboxUrl} aria-label="Ticket Sandbox"><TicketIcon /><span>Ticket Sandbox</span></a>
      <button type="button" disabled title="Раздел пока недоступен"><EscalationIcon /><span>Карта эскалаций</span></button>
      <button type="button" disabled title="Раздел пока недоступен"><AnalysisIcon /><span>Анализ тикетов</span></button>
      <a href={profile.achievementsUrl} aria-label="Достижения"><MedalIcon /><span>Достижения</span></a>
      <button type="button" disabled title="Раздел пока недоступен"><ProgressIcon /><span>Мой прогресс</span></button>
    </nav><footer><span>Roadmap 4.2</span><span>L1</span></footer></aside><main className="rm-main" onPointerMove={event => {
      if (event.pointerType !== 'mouse' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      const rect = event.currentTarget.getBoundingClientRect();
      setParallax({ x: ((event.clientX - rect.left) / rect.width - .5) * -12, y: ((event.clientY - rect.top) / rect.height - .5) * -10 });
    }} onPointerLeave={() => setParallax({ x: 0, y: 0 })}><div className="rm-background" aria-hidden="true" style={{ transform: `translate3d(${parallax.x}px,${parallax.y}px,0) scale(1.05)` }} />{children}</main></div>
  </div>;
}
