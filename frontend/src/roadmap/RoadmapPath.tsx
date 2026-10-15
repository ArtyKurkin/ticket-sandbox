import { useId } from 'react';
import type { Stage } from './types';
import { segmentLit } from './presentation';
import { RouteDefs } from './art/RouteDefs';
// Exact cubic control points from the approved Roadmap export.
export const routeSegments = [
  'M 156 189 C 215 220, 280 250, 348 280',
  'M 348 280 C 430 330, 490 120, 600 154',
  'M 600 154 C 710 188, 800 160, 888 210',
  'M 888 210 C 960 250, 1030 290, 1002 350',
  'M 1002 350 C 975 410, 910 460, 816 490',
  'M 816 490 C 730 518, 640 535, 528 532',
  'M 528 532 C 420 530, 310 540, 216 546',
] as const;
const completeRoute = routeSegments.map((segment, index) => index ? segment.slice(segment.indexOf('C')) : segment).join(' ');
export function RoadmapPath({ stages }: { stages: readonly Stage[] }) {
  const prefix = useId(); const url = (name: string) => `url(#${prefix}-${name})`;
  return <svg className="rm-path" aria-hidden="true" viewBox="0 0 1200 700" preserveAspectRatio="none">
    <RouteDefs prefix={prefix} />
    <path d="M 156 189 C 340 320, 420 120, 600 154 S 950 160, 1002 350 S 900 520, 816 490 S 450 560, 216 546" stroke="rgba(56,189,248,.04)" strokeWidth="36" fill="none" />
    <path d={completeRoute} stroke="rgba(15,23,42,.85)" strokeWidth="8" fill="none" />
    <path d={completeRoute} stroke="#18233c" strokeWidth="3.5" fill="none" />
    <path d={completeRoute} stroke={url('futureTrackGrad')} strokeWidth="2" strokeDasharray="6 8" fill="none" />
    {routeSegments.map((path, index) => <g key={path} className="rm-route-segment" data-lit={segmentLit(stages[index].data, stages[index + 1].data)} style={{ opacity: segmentLit(stages[index].data, stages[index + 1].data) ? 1 : 0 }}>
      <path d={path} stroke={url('ambientActiveGrad')} filter={url('ambientLineGlow')} strokeWidth="10" fill="none" />
      <path className="rm-route-fill" pathLength="1" d={path} stroke={url('activeStreamGrad')} filter={url('laserGlow')} strokeWidth="4.5" fill="none" style={{ strokeDashoffset: segmentLit(stages[index].data, stages[index + 1].data) ? 0 : 1 }} />
      <path className="rm-active-beam" d={path} stroke="#ffffff" strokeWidth="2" fill="none" />
    </g>)}
    {[[475,210],[750,180],[955,270],[930,425],[670,516],[370,537]].map(([x,y],index) => <circle key={x} cx={x} cy={y} r="3" fill={index === 5 ? '#a855f7' : index < 2 ? '#38bdf8' : '#64748b'} opacity=".9" />)}
  </svg>;
}
