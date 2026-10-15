import { NotificationError, type Notification, type NotificationApi } from './api';
export interface NotificationState { current: Notification | null; unread: number; busy: boolean; error: string | null; active: boolean }
export interface ControllerOptions {
  api: NotificationApi; changed: (state: NotificationState) => void; navigate: () => void; acknowledged?: (id: number) => void;
  uuid?: () => string; delay?: typeof setTimeout; cancel?: typeof clearTimeout;
}
// One sequential poll, one displayed event, explicit read acknowledgement, 3-event portions.
export class NotificationController {
  state: NotificationState = { current: null, unread: 0, busy: false, error: null, active: true };
  private seen = new Set<number>();
  private remaining = 3;
  private claimToken = '';
  private timer: ReturnType<typeof setTimeout> | undefined;
  private request = new AbortController();
  private stopped = false;
  private authPaused = false;
  private generation = 0;
  constructor(private options: ControllerOptions) {}
  private emit() { if (!this.stopped) this.options.changed({ ...this.state }); }
  private schedule() {
    if (!this.stopped && this.state.active && !this.authPaused) this.timer = (this.options.delay ?? setTimeout)(() => void this.poll(), 50000);
  }
  private clearTimer() { (this.options.cancel ?? clearTimeout)(this.timer); this.timer = undefined; }
  private fail(error: unknown) {
    if (this.request.signal.aborted || this.stopped) return;
    const e = error as NotificationError; this.state.error = e.message ?? 'Уведомления временно недоступны.';
    if (e.status === 401 || e.status === 403) { this.authPaused = true; this.state.current = null; }
  }
  async poll() {
    if (this.stopped || this.state.busy || !this.state.active || this.authPaused) return;
    this.clearTimer(); this.state.busy = true; this.emit();
    const generation = this.generation, signal = this.request.signal;
    try {
      if (this.state.current) {
        try {
          const current = await this.options.api.claim(this.state.current.eventId, this.claimToken, signal);
          if (signal.aborted || generation !== this.generation) return;
          this.state.current = current;
        } catch (error) {
          if ([404,409].includes((error as NotificationError).status)) this.state.current = null;
          else throw error;
        }
      }
      const data = await this.options.api.feed(signal);
      if (signal.aborted || generation !== this.generation) return;
      this.state.unread = data.unread; this.state.error = null;
      if (!this.state.current && this.remaining > 0) {
        for (const candidate of data.items) {
          if (this.seen.has(candidate.eventId)) continue;
          this.claimToken = (this.options.uuid ?? (() => crypto.randomUUID()))();
          try {
            const n = await this.options.api.claim(candidate.eventId, this.claimToken, signal);
            if (signal.aborted || generation !== this.generation) return;
            if (!n) { this.seen.add(candidate.eventId); continue; }
            this.state.current = n; this.remaining--; break;
          } catch (error) { if ([404,409].includes((error as NotificationError).status)) continue; throw error; }
        }
      }
    } catch (error) { if (!signal.aborted) this.fail(error); }
    finally {
      this.state.busy = false; this.emit();
      if (generation !== this.generation && this.state.active && !this.stopped) void this.poll(); else this.schedule();
    }
  }
  async dismiss(open = false) {
    const n = this.state.current;
    if (this.stopped || this.state.busy || !n || !this.state.active) return;
    this.clearTimer(); this.state.busy = true; this.emit();
    const generation = this.generation, signal = this.request.signal;
    let successful = false;
    try {
      await this.options.api.ack(n.eventId, this.claimToken, signal);
      if (signal.aborted || generation !== this.generation) return;
      this.seen.add(n.eventId); this.state.current = null; this.state.error = null;
      this.state.unread = Math.max(0, this.state.unread - 1); successful = true;
      this.options.acknowledged?.(n.eventId);
    } catch (error) { if (!signal.aborted) this.fail(error); }
    finally {
      this.state.busy = false; this.emit();
      if (generation !== this.generation && this.state.active && !this.stopped) void this.poll();
    }
    if (successful && open) { this.options.navigate(); return; }
    if (successful) await this.poll(); else this.schedule();
  }
  next() { this.remaining = 3; this.authPaused = false; this.state.error = null; void this.poll(); }
  setActive(active: boolean) {
    if (this.stopped || this.state.active === active) return;
    this.state.active = active;
    this.generation++;
    if (!active) { this.clearTimer(); this.request.abort(); }
    else { this.request = new AbortController(); if (!this.state.busy) void this.poll(); }
    this.emit();
  }
  externalAck(_id: number) {
    // BroadcastChannel is a wake-up hint. Only a server response can clear a toast.
    void this.poll();
  }
  stop() { this.stopped = true; this.clearTimer(); this.request.abort(); }
}
