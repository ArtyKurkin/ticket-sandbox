import { demoProgressOptions } from './data';
export function RoadmapDemoControls({ completed, onChange }: { completed: number | null; onChange: (value: number | null) => void }) {
  return <div className="rm-demo-controls" role="group" aria-label="Демонстрационный прогресс">
    <button type="button" aria-pressed={completed === null} onClick={() => onChange(null)}>Реальные данные</button>
    <span>Демо:</span>{demoProgressOptions.map(value =>
      <button type="button" key={value} aria-pressed={completed === value} onClick={() => onChange(value)}>{value}/8</button>)}
  </div>;
}
