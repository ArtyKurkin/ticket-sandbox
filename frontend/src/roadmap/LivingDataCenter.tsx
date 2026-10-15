import type { Stage } from './types';
import { sectorAwake } from './presentation';
const sectors = [
  { ids: ['training', 'sandbox'], name: 'alpha', points: [[31.5,45],[33,43],[20,48],[14,38]] },
  { ids: ['escalation', 'ticket_analysis'], name: 'bravo', points: [[76,34],[78.5,48],[66.5,36],[72,25]] },
  { ids: ['with_review', 'optional_review'], name: 'charlie', points: [[82,54],[74,62],[65,58],[85,68]] },
  { ids: ['no_review', 'probation'], name: 'delta', points: [[38,68],[26,74],[18,82],[45,72]] },
] as const;
export function LivingDataCenter({ stages }: { stages: readonly Stage[] }) {
  return <div className="rm-living" aria-hidden="true">{sectors.map(sector =>
    <div className={`rm-sector rm-sector-${sector.name}`} key={sector.name} data-awake={sectorAwake(stages, sector.ids)} style={{ opacity: sectorAwake(stages, sector.ids) ? (sector.name === 'delta' && stages.some(stage => stage.id === 'probation' && stage.data.state === 'completed') ? 1 : .85) : .2 }}>
      <span className="rm-sector-glow" />
      {sector.points.map(([x,y],index) => <i key={index} className={`rm-led rm-led-${index}`} style={{ left: `${x}%`, top: `${y}%` }} />)}
    </div>)}<span className="rm-floor-glow" /></div>;
}
