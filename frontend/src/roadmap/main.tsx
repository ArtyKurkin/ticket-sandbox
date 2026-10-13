import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RoadmapPage } from './RoadmapPage';
import type { RoadmapProps } from './types';
import './styles.css';
const container = document.querySelector('[data-react-island="roadmap"]');
const props = document.getElementById('roadmap-props');
if (container && props?.textContent) {
  createRoot(container).render(<StrictMode><RoadmapPage profile={JSON.parse(props.textContent) as RoadmapProps} /></StrictMode>);
}
