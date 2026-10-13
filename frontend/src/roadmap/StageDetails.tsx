import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Stage, StageStatus } from './types';
import { statusLabels } from './types';
import { positionCard, type Rect, type CardPosition } from './positioning';

export function StageDetails({ stage, status, surface, stationElements, onClose, sandboxUrl, demonstration, baseHeight, onReserveSpace }: {
  stage: Stage; status: StageStatus; surface: HTMLDivElement | null;
  stationElements: ReadonlyMap<string, HTMLButtonElement>; onClose: (returnFocus?: boolean) => void;
  sandboxUrl: string; demonstration: boolean; baseHeight: number; onReserveSpace: (height: number) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const [position, setPosition] = useState<CardPosition | null>(null);
  useLayoutEffect(() => {
    const card = ref.current, anchor = stationElements.get(stage.id);
    if (!card || !surface || !anchor) return;
    function update() {
      if (!card || !surface || !anchor) return;
      const canvas = surface.getBoundingClientRect();
      const relative = (element: HTMLElement): Rect => { const r = element.getBoundingClientRect(); return { left: r.left - canvas.left, top: r.top - canvas.top, width: r.width, height: r.height }; };
      const measured = card.getBoundingClientRect();
      const obstacles = [...stationElements.values()].flatMap(element => [...element.querySelectorAll<HTMLElement>('.rm-station-orbit, .rm-station-label')].map(relative));
      let next = positionCard({ width: canvas.width, height: baseHeight }, measured, relative(anchor), obstacles, stage.preferredSide);
      if (next.intersections > 0) {
        // Preserve route geometry; reserve scrollable space rather than cover a node.
        const extra = measured.height + 32;
        onReserveSpace(extra);
        next = positionCard({ width: canvas.width, height: baseHeight + extra }, measured, relative(anchor), obstacles, stage.preferredSide);
      } else onReserveSpace(0);
      setPosition(next);
    }
    update(); const observer = new ResizeObserver(update);
    observer.observe(surface); observer.observe(card);
    for (const element of stationElements.values()) observer.observe(element);
    return () => observer.disconnect();
  }, [stage, status, surface, stationElements, baseHeight, onReserveSpace]);
  useEffect(() => {
    if (position) ref.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [stage.id, position?.left, position?.top]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(true); };
    const outside = (event: PointerEvent) => {
      if (!(event.target instanceof Node) || ref.current?.contains(event.target)) return;
      if ([...stationElements.values()].some(element => element.contains(event.target as Node))) return;
      onClose(false);
    };
    document.addEventListener('keydown', onKey); document.addEventListener('pointerdown', outside);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', outside); };
  }, [onClose, stationElements]);
  const percent = status === 'completed' ? 100 : status === 'locked' ? 0 : stage.initialPercent;
  return <section ref={ref} id="rm-stage-details" role="dialog" aria-modal="false" aria-labelledby="rm-inspector-title"
    className={`rm-details rm-${status}`} data-intersections={position?.intersections}
    style={{ left: position?.left ?? 16, top: position?.top ?? 16, visibility: position ? 'visible' : 'hidden' }}>
    <header><span>ЭТАП {String(stage.order).padStart(2,'0')}</span><div><span className="rm-status-pill">● {statusLabels[status]}</span><button type="button" aria-label="Закрыть карточку этапа" onClick={() => onClose(true)}>×</button></div></header>
    <h2 id="rm-inspector-title">{stage.title}</h2><p>{stage.description}</p>
    {status === 'locked' && <div className="rm-condition">Условие: {stage.condition}</div>}
    <div className="rm-detail-progress"><span>Прогресс этапа</span><strong>{status === 'completed' && demonstration ? 'Завершено (100%)' : stage.metricLabel}</strong></div>
    <progress value={percent} max="100" aria-label="Прогресс этапа" />
    {stage.id === 'sandbox' && status !== 'locked' && !demonstration ? <a className="rm-stage-action" href={sandboxUrl}>{stage.actionLabel} ›</a> :
      <button type="button" className="rm-stage-action" disabled>{status === 'locked' ? 'Недоступно' : demonstration ? 'Демонстрационный режим' : stage.actionLabel}</button>}
  </section>;
}
