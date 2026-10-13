import { demoProgressOptions } from './data';
export function RoadmapDemoControls({ completed, onChange }: { completed: number; onChange: (value: number) => void }) {
  return <div className="rm-demo-controls" role="group" aria-label="Демонстрационный прогресс"><span>Демо:</span>{demoProgressOptions.map(value =>
    <button type="button" key={value} aria-pressed={completed === value} onClick={() => onChange(value)}>{value}/8{value === 1 ? ' (Текущий)' : ''}</button>)}</div>;
}
