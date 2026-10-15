import { useEffect, useRef, useState } from 'react';
import { TrophyUnlockToast } from '../achievements/TrophyUnlockToast';
import { metalLabels } from '../achievements/types';
import { asAchievement, createApi, safeRoomUrl, type NotificationConfig } from './api';
import { NotificationController, type NotificationState } from './controller';

export function NotificationHost({ config }: { config: NotificationConfig }) {
  const [state, setState] = useState<NotificationState>({ current: null, unread: 0, busy: false, error: null, active: true });
  const controller = useRef<NotificationController | null>(null);
  useEffect(() => {
    let channel: BroadcastChannel | null = null;
    try { if (typeof BroadcastChannel !== 'undefined') channel = new BroadcastChannel(`achievement-notifications:${config.userId}`); } catch { /* Server lease remains authoritative. */ }
    const client = new NotificationController({ api: createApi(config), changed: setState,
      navigate: () => location.assign(safeRoomUrl(config.trophyRoomUrl)),
      acknowledged: id => { try { channel?.postMessage({ acknowledged: id }); } catch { /* optional coordination */ } },
    });
    controller.current = client;
    const visible = () => document.visibilityState !== 'hidden' && document.querySelector('.tp-gallery[data-mode="demo"]') === null;
    const sync = () => client.setActive(visible());
    const hide = () => client.setActive(false);
    channel?.addEventListener('message', event => { if (Number.isSafeInteger(event.data?.acknowledged)) client.externalAck(event.data.acknowledged); });
    document.addEventListener('visibilitychange', sync); window.addEventListener('pagehide', hide); window.addEventListener('pageshow', sync);
    const observer = new MutationObserver(sync); observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['data-mode'] });
    client.setActive(visible()); void client.poll();
    return () => { client.stop(); channel?.close(); observer.disconnect(); document.removeEventListener('visibilitychange', sync); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', sync); controller.current = null; };
  }, [config]);
  if (!state.active) return null;
  const n = state.current;
  const description = n ? (n.action === 'upgrade' ? `${metalLabels[n.fromTier!.rarity]} → ${metalLabels[n.toTier.rarity]}` : metalLabels[n.toTier.rarity]) : '';
  return <aside className="an-host" aria-label="Новые достижения" data-notification-event={n?.eventId}>
    {n && <div className={`an-event an-${n.toTier.rarity}`} key={n.eventId}>
      <TrophyUnlockToast achievement={asAchievement(n)} autoDismiss={false} disabled={state.busy}
        notificationLabel={n.action === 'upgrade' ? 'Награда улучшена' : 'Достижение получено'}
        description={`${description} · Открыть Trophy Room`} onDismiss={() => void controller.current?.dismiss()}
        onOpen={() => void controller.current?.dismiss(true)} />
    </div>}
    {state.error && <div className="an-status" role="status"><p>{state.error}</p>
      <button type="button" disabled={state.busy} onClick={() => controller.current?.next()}>Проверить снова</button></div>}
    {!n && state.unread > 0 && !state.error && <button type="button" className="an-more" disabled={state.busy}
      onClick={() => controller.current?.next()}>Показать новые уведомления ({state.unread})</button>}
  </aside>;
}
