import type { Achievement } from './types';
import { cardStatus, displayMetal, displayTitle, isHidden, metalLabels } from './types';
import { TrophyMedallion } from './TrophyMedallion';

export function TrophyCard({ achievement, glowing, onOpen }: {
  achievement: Achievement; glowing: boolean; onOpen: (item: Achievement) => void;
}) {
  const hidden = isHidden(achievement);
  const earned = achievement.status === 'earned';
  const metal = displayMetal(achievement);
  return <button type="button" className={`tp-trophy-card tp-${hidden ? 'secret' : metal ?? 'neutral'} ${earned ? 'tp-earned' : 'tp-locked'} ${glowing ? 'tp-unlock-glow' : ''}`}
    onClick={() => onOpen(achievement)} data-achievement-id={achievement.id} data-status={achievement.status}>
    <span className="tp-gleam" aria-hidden="true" />
    <span className="tp-card-art"><TrophyMedallion achievement={achievement} /></span>
    <span className="tp-card-caption">
      <span className="tp-card-title">{displayTitle(achievement)}</span>
      <span className="tp-card-meta"><span className="tp-metal-badge">{hidden ? 'Скрыто' : metal ? metalLabels[metal] : 'Уровень не получен'}</span>
        <span className="tp-card-status">{earned && <span aria-hidden="true" className="tp-check">✓</span>}{cardStatus(achievement)}</span>
      </span>
      {!hidden && achievement.dataQuality === 'disputed' && <span className="tp-disputed">Результат требует проверки</span>}
      {!hidden && achievement.progress && <span className="tp-card-status">{achievement.progress.label}</span>}
    </span>
  </button>;
}
