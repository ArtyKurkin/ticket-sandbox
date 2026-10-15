import { useEffect, useRef, useState } from 'react';
import type { Achievement } from './types';
import { TrophyMedallion } from './TrophyMedallion';

export function TrophyUnlockToast({ achievement, description, onOpen, onDismiss, demonstration = false, notificationLabel, autoDismiss = true, disabled = false }: {
  achievement: Achievement; description: string; onOpen: () => void; onDismiss: () => void; demonstration?: boolean; notificationLabel?: string; autoDismiss?: boolean; disabled?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const remaining = useRef(5000);
  const paused = hovered || focused;
  useEffect(() => {
    if (paused || !autoDismiss) return;
    const start = performance.now();
    const timer = window.setTimeout(onDismiss, remaining.current);
    return () => { window.clearTimeout(timer); remaining.current = Math.max(0, remaining.current - (performance.now() - start)); };
  }, [paused, onDismiss, autoDismiss]);
  return <div className="tp-unlock-toast" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocus={() => setFocused(true)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}>
    <span className="tp-sr-only" role="status">{demonstration ? 'Демонстрация получения' : notificationLabel ?? 'Трофей разблокирован'}: {achievement.title}</span>
    <button type="button" className="tp-toast-open" onClick={onOpen} disabled={disabled}>
      <span className="tp-toast-art"><TrophyMedallion achievement={achievement} /></span>
      <span className="tp-toast-copy"><span>{demonstration ? '● ДЕМОНСТРАЦИЯ ПОЛУЧЕНИЯ' : notificationLabel ?? '● ТРОФЕЙ РАЗБЛОКИРОВАН!'}</span><strong>{achievement.title}</strong><small>{description}</small></span>
    </button>
    <button type="button" className="tp-toast-dismiss" aria-label="Скрыть уведомление" onClick={onDismiss} disabled={disabled}>×</button>
  </div>;
}
