import { createRoot } from 'react-dom/client';
import { NotificationHost } from './NotificationHost';
import type { NotificationConfig } from './api';
import '../achievements/styles.css';
import './styles.css';

export function mountNotificationHost() {
  const root = document.getElementById('achievement-notification-host');
  const config = document.getElementById('achievement-notification-config');
  if (!root || !config?.textContent || document.documentElement.dataset.achievementNotifications === 'mounted') return;
  document.documentElement.dataset.achievementNotifications = 'mounted';
  createRoot(root).render(<NotificationHost config={JSON.parse(config.textContent) as NotificationConfig} />);
}
mountNotificationHost();
