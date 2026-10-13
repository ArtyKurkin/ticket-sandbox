import type { Achievement, Metal, MetalFilter, StatusFilter } from './types';
import { matchesFilters, metalLabels } from './types';

export function TrophyFilters({ items, status, metal, onStatus, onMetal }: {
  items: readonly Achievement[]; status: StatusFilter; metal: MetalFilter;
  onStatus: (value: StatusFilter) => void; onMetal: (value: MetalFilter) => void;
}) {
  const statuses: [StatusFilter, string][] = [['all', 'Все'], ['earned', 'Полученные'], ['locked', 'Не полученные'], ['secret', 'Секретные']];
  return <div className="tp-filters">
    <div className="tp-status-filters" role="group" aria-label="Статус достижения">{statuses.map(([value, label]) =>
      <button type="button" key={value} aria-pressed={status === value} onClick={() => onStatus(value)}>{label} ({items.filter(item => matchesFilters(item, value, 'all')).length})</button>)}</div>
    <div className="tp-metal-filters" role="group" aria-label="Категория металла">
      <button type="button" aria-pressed={metal === 'all'} onClick={() => onMetal('all')}>Все типы</button>
      {(Object.keys(metalLabels) as Metal[]).map(value => <button type="button" className={`tp-${value}`} key={value} aria-pressed={metal === value} onClick={() => onMetal(value)}>{metalLabels[value]}</button>)}
    </div>
  </div>;
}
