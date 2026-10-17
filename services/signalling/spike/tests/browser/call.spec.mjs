import { test, expect } from '@playwright/test';

test('two clients exchange media, export redacted stats, toggle controls and rejoin', async ({ browser }, testInfo) => {
  const context = await browser.newContext({ permissions: ['camera', 'microphone'], acceptDownloads: true });
  const a = await context.newPage();
  const b = await context.newPage();
  const errors = [];
  for (const page of [a, b]) {
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('http://127.0.0.1:9000');
    if (process.env.SPIKE_TEST_TURN_URL) {
      await page.locator('#urls').fill(process.env.SPIKE_TEST_TURN_URL);
      await page.locator('#username').fill(process.env.SPIKE_TEST_TURN_USERNAME);
      await page.locator('#credential').fill(process.env.SPIKE_TEST_TURN_CREDENTIAL);
      await page.locator('#relay').check();
    }
    await page.locator('#start').click();
    await expect(page.locator('#status')).toHaveText('Ready');
  }
  const call = async () => {
    await a.locator('#remote-id').fill(await b.locator('#peer-id').textContent());
    await a.locator('#call').click();
    for (const page of [a, b]) {
      await expect.poll(() => page.locator('#stats').textContent()).toContain('"connectionState": "connected"');
      await expect.poll(() => page.evaluate(() => {
        const video = document.getElementById('remote');
        return video.videoWidth > 0 && video.currentTime > 0;
      })).toBe(true);
      await expect.poll(() => page.locator('#stats').textContent()).toContain('framesDecoded');
      await expect.poll(async () => {
        const stats = JSON.parse(await page.locator('#stats').textContent());
        return ['audio', 'video'].every((kind) =>
          stats.rtp.some((r) => r.kind === kind && r.bytesReceived > 0)
          && stats.rtp.some((r) => r.kind === kind && r.bytesSent > 0));
      }).toBe(true);
      if (process.env.SPIKE_TEST_TURN_URL) {
        await expect.poll(async () => JSON.parse(await page.locator('#stats').textContent()).selectedPair?.local?.candidateType).toBe('relay');
      }
    }
  };
  await call();
  await a.locator('#mic').click();
  await expect(a.locator('#mic')).toHaveText('Unmute microphone');
  expect(await a.evaluate(() => document.getElementById('local').srcObject.getAudioTracks()[0].enabled)).toBe(false);
  await a.locator('#camera').click();
  expect(await a.evaluate(() => document.getElementById('local').srcObject.getVideoTracks()[0].enabled)).toBe(false);
  await a.locator('#mic').click();
  await a.locator('#camera').click();
  const downloadPromise = a.waitForEvent('download');
  await a.locator('#export').click();
  const download = await downloadPromise;
  const readable = await download.createReadStream();
  const chunks = [];
  for await (const chunk of readable) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString();
  const evidence = JSON.parse(body);
  await testInfo.attach('caller-evidence', { body, contentType: 'application/json' });
  expect(evidence.iceTransportPolicy).toBe(process.env.SPIKE_TEST_TURN_URL ? 'relay' : 'all');
  expect(evidence.samples.some((sample) => sample.selectedPair?.state === 'succeeded')).toBe(true);
  expect(body).not.toMatch(/credential|username|"address"|"ip"|"peerId"/);
  await a.locator('#leave').click();
  expect(await a.evaluate(() => document.getElementById('local').srcObject)).toBe(null);
  await expect(b.locator('#call')).toBeEnabled();
  if (process.env.SPIKE_TEST_TURN_URL) await a.locator('#credential').fill(process.env.SPIKE_TEST_TURN_CREDENTIAL);
  await a.locator('#start').click();
  await expect(a.locator('#status')).toHaveText('Ready');
  await call();
  for (const page of [a, b]) await page.locator('#leave').click();
  expect(errors).toEqual([]);
  await context.close();
});

test('forced relay cannot silently fall back to a direct call', async ({ page }) => {
  await page.goto('/');
  await page.locator('#relay').check();
  await page.locator('#start').click();
  await expect(page.locator('#status')).toHaveText('Forced relay requires TURN settings');
  await expect(page.locator('#start')).toBeEnabled();
  await expect(page.locator('#call')).toBeDisabled();
});

test('invalid TURN credentials cannot connect in relay-only mode', async ({ browser }) => {
  test.skip(!process.env.SPIKE_TEST_TURN_URL, 'Requires an actual coturn instance');
  const context = await browser.newContext({ permissions: ['camera', 'microphone'] });
  const pages = [await context.newPage(), await context.newPage()];
  for (const page of pages) {
    await page.goto('http://127.0.0.1:9000');
    await page.locator('#urls').fill(process.env.SPIKE_TEST_TURN_URL);
    await page.locator('#username').fill(process.env.SPIKE_TEST_TURN_USERNAME);
    await page.locator('#credential').fill('deliberately-invalid-password');
    await page.locator('#relay').check();
    await page.locator('#start').click();
    await expect(page.locator('#status')).toHaveText('Ready');
  }
  await pages[0].locator('#remote-id').fill(await pages[1].locator('#peer-id').textContent());
  await pages[0].locator('#call').click();
  await pages[0].waitForTimeout(8000);
  for (const page of pages) {
    const stats = JSON.parse(await page.locator('#stats').textContent());
    expect(stats.selectedPair).toBe(null);
    expect(stats.connectionState).not.toBe('connected');
    expect(stats.rtp.some((rtp) => rtp.bytesReceived > 0)).toBe(false);
    expect(await page.evaluate(() => document.getElementById('remote').videoWidth)).toBe(0);
    await page.locator('#leave').click();
  }
  await context.close();
});
