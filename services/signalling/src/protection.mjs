// ECS injects this local agent endpoint. Protection covers planned scale-in and
// deployments; failures still require the browser's fresh-admission recovery.
export class TaskProtection {
  constructor(uri = process.env.ECS_AGENT_URI, request = fetch) {
    this.uri = uri;
    this.request = request;
    this.enabledUntil = 0;
    this.pending = null;
    if (uri) {
      const url = new URL(uri);
      if (url.protocol !== 'http:' || url.hostname !== '169.254.170.2'
        || url.username || url.password || url.search || url.hash) throw new Error('Invalid ECS agent');
    }
  }

  async update(enabled) {
    if (!this.uri) return;
    const response = await this.request(`${this.uri}/task-protection/v1/state`, {
      method: 'PUT', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ProtectionEnabled: enabled, ExpiresInMinutes: 2 }),
      signal: AbortSignal.timeout(3000), redirect: 'error',
    });
    if (!response.ok) throw new Error('Task protection unavailable');
    const result = await response.json();
    if (result.protection?.ProtectionEnabled !== enabled || result.failure || result.error) {
      throw new Error('Task protection rejected');
    }
    this.enabledUntil = enabled ? Date.now() + 90000 : 0;
  }

  async ensure() {
    while (this.pending) await this.pending;
    if (!this.uri || Date.now() < this.enabledUntil) return;
    this.pending = this.update(true).finally(() => { this.pending = null; });
    await this.pending;
  }

  async release() {
    while (this.pending) await this.pending;
    if (!this.enabledUntil) return;
    this.pending = this.update(false).finally(() => { this.pending = null; });
    await this.pending;
  }
}
