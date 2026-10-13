import type { Achievement } from './types';
import { displayTitle, isHidden, metalLabels } from './types';
import { TrophyMedallion } from './TrophyMedallion';

export function TrophyCard({ achievement, glowing, onOpen }: {
  achievement: Achievement; glowing: boolean; onOpen: (item: Achievement) => void;
}) {
  const hidden = isHidden(achievement);
  const earned = achievement.status === 'earned';
  const status = earned ? `Получено ${achievement.earnedAt}` : hidden ? 'Засекречено' :
    `Не получено • ${achievement.progress.summary ?? `Прогресс ${Math.round(achievement.progress.percent)}%`}`;
  return <button type="button" className={`tp-trophy-card tp-${hidden ? 'secret' : achievement.metal} ${earned ? 'tp-earned' : 'tp-locked'} ${glowing ? 'tp-unlock-glow' : ''}`}
    onClick={() => onOpen(achievement)} data-achievement-id={achievement.id}>
    <span className="tp-gleam" aria-hidden="true" />
    <span className="tp-card-art"><TrophyMedallion achievement={achievement} /></span>
    <span className="tp-card-caption">
      <span className="tp-card-title">{displayTitle(achievement)}</span>
      <span className="tp-card-meta"><span className="tp-metal-badge">{hidden ? 'Скрыто' : metalLabels[achievement.metal]}</span>
        <span className="tp-card-status">{earned && <span aria-hidden="true" className="tp-check">✓</span>}{status}</span>
      </span>
    </span>
  </button>;
}
