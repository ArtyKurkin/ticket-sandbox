import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { Stage } from './types';
import type { Journey } from './apiTypes';
import { stageStatus } from './types';
import { RoadmapPath } from './RoadmapPath';
import { RoadmapStation } from './RoadmapStation';
import { StageDetails } from './StageDetails';
import { LivingDataCenter } from './LivingDataCenter';

export function RoadmapCanvas({ stages, journey, demonstration }: { stages: readonly Stage[]; journey: Journey | null; demonstration: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [baseHeight, setBaseHeight] = useState(730);
  const [reservedSpace, setReservedSpace] = useState(0);
  useLayoutEffect(() => {
    const viewport = viewportRef.current; if (!viewport) return;
    const observer = new ResizeObserver(() => setBaseHeight(Math.max(730, viewport.clientHeight)));
    observer.observe(viewport); return () => observer.disconnect();
  }, []);
  const [selected, setSelected] = useState<string | null>(null);
  const [surface, setSurface] = useState<HTMLDivElement | null>(null);
  const stationElements = useRef(new Map<string, HTMLButtonElement>());
  const close = useCallback((returnFocus = false) => {
    if (returnFocus && selected) stationElements.current.get(selected)?.focus();
    setSelected(null); setReservedSpace(0);
  }, [selected]);
  const stage = stages.find(item => item.id === selected);
  return <div className="rm-canvas-scroll" ref={viewportRef} tabIndex={0} aria-label="Карта дата-центра: восемь этапов, область прокручивается">
    <div className="rm-canvas" ref={setSurface} style={{ height: baseHeight + reservedSpace }}>
      <div className="rm-coordinate-layer" style={{ height: baseHeight }}>
        <LivingDataCenter stages={stages} />
        <RoadmapPath stages={stages} />
        {stages.map(item => <RoadmapStation key={item.id} stage={item} status={stageStatus(item, journey)} selected={selected === item.id}
          elementRef={element => { if (element) stationElements.current.set(item.id, element); else stationElements.current.delete(item.id); }}
          onSelect={value => setSelected(value.id)} />)}
      </div>
      {stage && <StageDetails baseHeight={baseHeight} onReserveSpace={setReservedSpace} stage={stage} status={stageStatus(stage, journey)} surface={surface} stationElements={stationElements.current}
        journey={journey} demonstration={demonstration} onClose={close} />}
    </div>
  </div>;
}
