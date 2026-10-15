import type { CSSProperties } from 'react';
import type { Metal } from './types';

const tones = {
  bronze: { rim: ['#fef08a', '#f59e0b', '#b45309', '#78350f', '#451a03'], bevel: ['#fed7aa', '#d97706', '#78350f', '#2a0f02'], core: ['#552206', '#270e03', '#140601'], accent: '#f59e0b' },
  silver: { rim: ['#ffffff', '#e2e8f0', '#94a3b8', '#475569', '#1e293b'], bevel: ['#f8fafc', '#94a3b8', '#334155', '#0f172a'], core: ['#1e293b', '#0f172a', '#020617'], accent: '#38bdf8' },
  gold: { rim: ['#fef08a', '#eab308', '#a16207', '#713f12', '#3b1d03'], bevel: ['#fef9c3', '#ca8a04', '#713f12', '#241002'], core: ['#3d1e05', '#1e0c02', '#0a0401'], accent: '#facc15' },
  platinum: { rim: ['#ffffff', '#e0e7ff', '#818cf8', '#38bdf8', '#312e81'], bevel: ['#f5f3ff', '#a855f7', '#4338ca', '#0f172a'], core: ['#1e1b4b', '#090817', '#020108'], accent: '#38bdf8' },
  neutral: { rim: ['#94a3b8', '#64748b', '#334155', '#1e293b', '#0f172a'], bevel: ['#64748b', '#475569', '#1e293b', '#0f172a'], core: ['#131d2e', '#0b101c', '#040711'], accent: '#64748b' },
} as const;
export function paletteStyle(metal: Metal | null): CSSProperties {
  const tone = tones[metal ?? 'neutral'];
  const result: Record<string, string> = {};
  for (const group of ['rim', 'bevel', 'core'] as const) tone[group].forEach((color, index) => { result[`--tp-metal-${group}-${index}`] = color; });
  Object.assign(result, { '--tp-metal-shine': tone.rim[0], '--tp-metal-highlight': tone.bevel[0],
    '--tp-metal-mid': tone.rim[2], '--tp-metal-low': tone.rim[3], '--tp-metal-dark': tone.core[0],
    '--tp-metal-shadow': tone.core[2], '--tp-metal-accent': tone.accent });
  return result as CSSProperties;
}
