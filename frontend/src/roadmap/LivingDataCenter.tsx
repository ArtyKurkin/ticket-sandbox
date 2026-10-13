const sectors = [
  { threshold: 0, name: 'alpha', points: [[31.5,45],[33,43],[20,48],[14,38]] },
  { threshold: 2, name: 'bravo', points: [[76,34],[78.5,48],[66.5,36],[72,25]] },
  { threshold: 4, name: 'charlie', points: [[82,54],[74,62],[65,58],[85,68]] },
  { threshold: 6, name: 'delta', points: [[38,68],[26,74],[18,82],[45,72]] },
] as const;
export function LivingDataCenter({ completed }: { completed: number }) {
  return <div className="rm-living" aria-hidden="true">{sectors.map(sector =>
    <div className={`rm-sector rm-sector-${sector.name}`} key={sector.name} data-awake={completed >= sector.threshold} style={{ opacity: completed >= sector.threshold ? (sector.name === 'delta' && completed >= 7 ? 1 : .85) : .2 }}>
      <span className="rm-sector-glow" />
      {sector.points.map(([x,y],index) => <i key={index} className={`rm-led rm-led-${index}`} style={{ left: `${x}%`, top: `${y}%` }} />)}
    </div>)}<span className="rm-floor-glow" /></div>;
}
