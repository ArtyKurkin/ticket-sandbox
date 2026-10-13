import { useState } from 'react';
import type { RoadmapProps } from './types';
import { RoadmapShell } from './RoadmapShell';
import { RoadmapDemoControls } from './RoadmapDemoControls';
import { RoadmapCanvas } from './RoadmapCanvas';

export function RoadmapPage({ profile }: { profile: RoadmapProps }) {
  // Django-provided initial state is separate from the local staff simulation.
  const [demoCompleted, setDemoCompleted] = useState<number | null>(null);
  const completed = profile.canDemo && demoCompleted !== null ? demoCompleted : profile.initialProgress.completed;
  const trophies = demoCompleted === null ? profile.initialProgress.trophyCount : completed >= 8 ? 8 : completed >= 6 ? 6 : completed >= 3 ? 4 : 2;
  const percent = completed / 8 * 100;
  return <RoadmapShell profile={profile}>
    <div className="rm-toolbar"><h1>Roadmap стажёра <span>Интерактивная карта</span></h1><div className="rm-toolbar-metrics">
      {profile.canDemo && <RoadmapDemoControls completed={completed} onChange={setDemoCompleted} />}
      <div className="rm-overall-progress"><span>{completed} из 8 этапов</span><progress max="8" value={completed} aria-label="Общий прогресс" /><strong>{percent.toLocaleString('ru-RU')}%</strong></div>
      <a className="rm-trophies" href={profile.achievementsUrl}><svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><path d="M19 4h-2V2H7v2H5c-1.1 0-2 .9-2 2v3c0 2.5 1.9 4.6 4.3 4.9.7 1.4 2 2.5 3.7 2.9V19H8v2h8v-2h-3v-2.2c1.7-.4 3-1.5 3.7-2.9 2.4-.3 4.3-2.4 4.3-4.9V6c0-1.1-.9-2-2-2zM5 9V6h2v4.8C5.8 10.4 5 9.8 5 9zm14 0c0 .8-.8 1.4-2 1.8V6h2v3z" /></svg><span>{trophies} {trophies === 2 || trophies === 4 ? 'трофея' : 'трофеев'}</span></a>
    </div></div>
    <RoadmapCanvas completed={completed} sandboxUrl={profile.sandboxUrl} demonstration={demoCompleted !== null} />
  </RoadmapShell>;
}
