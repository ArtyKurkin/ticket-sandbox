import type { Side } from './types';
export interface Rect { left: number; top: number; width: number; height: number }
export interface CardPosition { left: number; top: number; intersections: number }
const overlap = (a: Rect, b: Rect) => Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));

/** Measure first; consider all station + label rectangles, not only the selected node. */
export function positionCard(bounds: { width: number; height: number }, card: { width: number; height: number }, anchor: Rect, obstacles: readonly Rect[], preferred: Side): CardPosition {
  const margin = 16, gap = 18;
  const clampX = (value: number) => Math.max(margin, Math.min(value, bounds.width - card.width - margin));
  const clampY = (value: number) => Math.max(margin, Math.min(value, bounds.height - card.height - margin));
  const centerX = anchor.left + anchor.width / 2 - card.width / 2;
  const centerY = anchor.top + anchor.height / 2 - card.height / 2;
  const sides: Record<Side, { left: number; top: number }> = {
    right: { left: anchor.left + anchor.width + gap, top: centerY },
    left: { left: anchor.left - card.width - gap, top: centerY },
    top: { left: centerX, top: anchor.top - card.height - gap },
    bottom: { left: centerX, top: anchor.top + anchor.height + gap },
  };
  const preference = sides[preferred];
  const candidates = [preference, ...Object.values(sides)];
  const xs = [margin, bounds.width - card.width - margin, centerX, ...obstacles.flatMap(o => [o.left - card.width - gap, o.left + o.width + gap])];
  const ys = [margin, bounds.height - card.height - margin, centerY, ...obstacles.flatMap(o => [o.top - card.height - gap, o.top + o.height + gap])];
  for (const left of xs) for (const top of ys) candidates.push({ left, top });
  const scored = candidates.map(candidate => {
    const rect = { left: clampX(candidate.left), top: clampY(candidate.top), width: card.width, height: card.height };
    const areas = obstacles.map(obstacle => overlap(rect, { left: obstacle.left - 8, top: obstacle.top - 8, width: obstacle.width + 16, height: obstacle.height + 16 }));
    return { ...rect, intersections: areas.filter(area => area > 0).length, area: areas.reduce((a,b) => a+b,0), distance: Math.hypot(rect.left - preference.left, rect.top - preference.top) };
  });
  scored.sort((a,b) => a.intersections - b.intersections || a.area - b.area || a.distance - b.distance);
  return { left: scored[0].left, top: scored[0].top, intersections: scored[0].intersections };
}
