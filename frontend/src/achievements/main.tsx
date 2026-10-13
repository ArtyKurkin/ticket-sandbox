import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { TrophyRoom } from './TrophyRoom';
import type { TrophyPageProps } from './TrophyShell';
import './styles.css';

const container = document.querySelector('[data-react-island="trophy-room"]');
const propsElement = document.getElementById('trophy-room-props');
if (container && propsElement?.textContent) {
  const profile = JSON.parse(propsElement.textContent) as TrophyPageProps;
  createRoot(container).render(<StrictMode><TrophyRoom profile={profile} /></StrictMode>);
}
