import { useEffect, useRef } from 'react';
import type { Achievement } from './types';
import { displayTitle, isHidden, metalLabels } from './types';
import { TrophyMedallion } from './TrophyMedallion';

export function TrophyDetails({ achievement, onClose, returnFocus }: { achievement: Achievement; onClose: () => void; returnFocus: HTMLElement | null }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const hidden = isHidden(achievement);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = returnFocus ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    dialog?.showModal();
    closeRef.current?.focus();
    return () => { dialog?.close(); previousFocus?.focus(); };
  }, []);
  return <dialog ref={dialogRef} className={`tp-details tp-${hidden ? 'secret' : achievement.metal}`}
    aria-labelledby="tp-details-title" aria-describedby="tp-details-description"
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const buttons = dialogRef.current?.querySelectorAll<HTMLButtonElement>('button');
      if (!buttons?.length) return;
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
    }}>
    <button type="button" ref={closeRef} className="tp-close" aria-label="Закрыть подробности" onClick={onClose}>×</button>
    <div className="tp-detail-art"><TrophyMedallion achievement={achievement} /></div>
    <div className="tp-detail-heading"><span className="tp-metal-badge">{hidden ? 'Скрыто' : metalLabels[achievement.metal]}</span>{achievement.earnedAt && <span>Получено: {achievement.earnedAt}</span>}</div>
    <h2 id="tp-details-title">{displayTitle(achievement)}</h2>
    <p id="tp-details-description">{hidden ? 'Это достижение скрыто. Подробности станут доступны после его получения.' : achievement.description}</p>
    {!hidden && achievement.mentorComment && <blockquote className="tp-mentor"><strong>✓ Оценка наставника Timeweb Cloud</strong><p>{achievement.mentorComment.text}</p><footer>{achievement.mentorComment.author}<span>Отдел сопровождения</span></footer></blockquote>}
    <div className="tp-detail-progress">
      <span className="tp-muted">{achievement.status === 'earned' ? 'Получено' : 'Не получено'}{!hidden && achievement.manualGrant && ' • Выдаётся наставником'}</span>
      <p>Условие получения:</p><strong>{hidden ? 'Условие засекречено' : achievement.condition}</strong>
      <p>{hidden ? 'Прогресс скрыт' : achievement.progress.label}</p>
      {!hidden && <progress max="100" value={achievement.progress.percent} aria-label="Прогресс достижения" />}
    </div>
    <div className="tp-detail-footer"><button type="button" onClick={onClose}>Закрыть</button></div>
  </dialog>;
}
