import { useMemo, useState } from 'react';
import type { RoadmapProps } from './types';
import { RoadmapShell } from './RoadmapShell';
import { RoadmapDemoControls } from './RoadmapDemoControls';
import { RoadmapCanvas } from './RoadmapCanvas';
import { useRoadmap } from './useRoadmap';
import { demoStages, formatPercent, mapStations } from './presentation';

export function RoadmapPage({ profile }: { profile: RoadmapProps }) {
  const { state, retry } = useRoadmap(profile.roadmapApiUrl, profile.actionExternalHosts);
  const [demoCompleted, setDemoCompleted] = useState<number | null>(null);
  const demonstration = profile.canDemo && demoCompleted !== null;
  const realData = state.status === 'success' ? state.data : null;
  const stations = useMemo(() => demonstration ? demoStages(demoCompleted!) : realData ? mapStations(realData) : null, [demonstration, demoCompleted, realData]);
  return <RoadmapShell profile={profile}>
    <div className="rm-toolbar"><h1>Roadmap стажёра <span>{demonstration ? 'Демонстрация' : 'Интерактивная карта'}</span></h1>
      <div className="rm-toolbar-metrics">
        {profile.canDemo && <RoadmapDemoControls completed={demonstration ? demoCompleted : null} onChange={setDemoCompleted} />}
        {demonstration ? <div className="rm-overall-progress"><span>Демо: {demoCompleted} из 8 станций</span><progress max="8" value={demoCompleted!} aria-label="Демонстрационный прогресс" /></div> :
          realData && realData.journey.state !== 'not_started' && <div className="rm-overall-progress">
            <span>{realData.overall.completed_count} из {realData.overall.applicable_count} этапов</span>
            <progress max="100" value={realData.overall.percent} aria-label="Общий прогресс" />
            <strong>{formatPercent(realData.overall.percent)}%</strong>
          </div>}
      </div>
    </div>
    {!demonstration && state.status === 'loading' && <div className="rm-api-message" role="status">Загружаем Roadmap…</div>}
    {!demonstration && state.status === 'error' && <div className="rm-api-message" role="alert">
      <p>{state.error.message}</p>
      {state.error.kind === 'unauthorized' ? <a className="rm-stage-action" href={profile.loginUrl}>Войти</a> : <button className="rm-stage-action" onClick={retry}>Повторить загрузку</button>}
    </div>}
    {!demonstration && realData && <div className="rm-journey-message" role="status">
      {realData.journey.state === 'not_started' ? 'Адаптация ещё не началась. Прогресс появится после создания адаптации.' :
        realData.journey.state === 'terminated' ? 'Испытательный срок прекращён.' :
        realData.journey.state === 'insufficient_data' ? 'Подтверждённый исторический результат ИС отсутствует.' :
        realData.journey.state === 'success' ? 'Испытательный срок успешно завершён.' :
        realData.journey.current_stage ? `Текущий этап: ${realData.journey.current_stage.title}` : ''}
      {realData.data_quality.some(item => item.code === 'ambiguous_stage_history') && <span>История содержит пробелы. Показаны только подтверждённые завершения.</span>}
    </div>}
    {demonstration && <div className="rm-journey-message" role="status">Демонстрационный режим · данные обучения и достижения не изменяются.</div>}
    {stations && <RoadmapCanvas stages={stations} journey={demonstration ? null : realData!.journey} demonstration={demonstration} />}
  </RoadmapShell>;
}
