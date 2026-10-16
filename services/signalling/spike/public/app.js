const $ = (id) => document.getElementById(id);
let peer, stream, call, timer;
let starting = false;
let generation = 0;
let evidence = {};
let events = [];

function log(message) {
  events.push({ at: new Date().toISOString(), message });
  events = events.slice(-100);
  $('events').textContent = events.map((event) => `${event.at} ${event.message}`).join('\n');
}
function status(message) { $('status').textContent = message; log(message); }
function controls() {
  const ready = Boolean(peer?.open && stream);
  $('start').disabled = starting || Boolean(peer);
  $('settings').disabled = starting || Boolean(peer);
  $('leave').disabled = !starting && !peer && !stream;
  $('call').disabled = !ready || Boolean(call);
  $('hangup').disabled = !call;
  $('mic').disabled = $('camera').disabled = !stream;
}
function endCall(close = true) {
  const old = call;
  call = undefined;
  clearInterval(timer);
  timer = undefined;
  if (close) old?.close();
  $('remote').srcObject = null;
  controls();
}
function leave() {
  generation++;
  endCall();
  peer?.destroy();
  peer = undefined;
  stream?.getTracks().forEach((track) => track.stop());
  stream = undefined;
  starting = false;
  $('local').srcObject = null;
  $('peer-id').textContent = '—';
  controls();
  status('Left; camera and microphone released');
}

async function sample(activeCall) {
  const pc = activeCall.peerConnection;
  if (!pc || activeCall !== call) return;
  const reports = await pc.getStats();
  if (activeCall !== call) return;
  const transport = [...reports.values()].find((r) => r.type === 'transport' && r.selectedCandidatePairId);
  const pair = transport ? reports.get(transport.selectedCandidatePairId)
    : [...reports.values()].find((r) => r.type === 'candidate-pair' && r.nominated && r.state === 'succeeded');
  const candidate = (id) => {
    const value = reports.get(id);
    return value ? { candidateType: value.candidateType, protocol: value.protocol,
      relayProtocol: value.relayProtocol } : null;
  };
  const rtp = [...reports.values()].filter((r) => ['inbound-rtp', 'outbound-rtp'].includes(r.type))
    .map((r) => ({ direction: r.type, kind: r.kind, bytesReceived: r.bytesReceived,
      bytesSent: r.bytesSent, packetsReceived: r.packetsReceived, packetsSent: r.packetsSent,
      framesDecoded: r.framesDecoded, framesEncoded: r.framesEncoded }));
  const entry = { at: new Date().toISOString(), callNumber: evidence.calls.length, connectionState: pc.connectionState,
    iceConnectionState: pc.iceConnectionState,
    selectedPair: pair ? { state: pair.state, local: candidate(pair.localCandidateId),
      remote: candidate(pair.remoteCandidateId), bytesSent: pair.bytesSent,
      bytesReceived: pair.bytesReceived, currentRoundTripTime: pair.currentRoundTripTime } : null, rtp };
  evidence.samples.push(entry);
  evidence.samples = evidence.samples.slice(-600);
  $('stats').textContent = JSON.stringify(entry, null, 2);
}
function attachCall(incoming) {
  call = incoming;
  evidence.calls.push({ at: new Date().toISOString(), callNumber: evidence.calls.length + 1 });
  incoming.on('stream', (remote) => {
    if (call !== incoming) return;
    $('remote').srcObject = remote;
    $('remote').play().catch(() => log('Remote autoplay blocked; press play on the remote video'));
    status('Remote stream attached; verify sound and moving video at both ends');
  });
  incoming.on('close', () => {
    if (call === incoming) { endCall(false); status('Call ended'); }
  });
  incoming.on('error', (error) => {
    if (call === incoming) { endCall(); status(`Call error: ${error.type || 'unknown'}`); }
  });
  timer = setInterval(() => sample(incoming).catch(() => log('Statistics unavailable')), 1000);
  controls();
}

$('start').onclick = async () => {
  const attempt = ++generation;
  starting = true;
  controls();
  try {
    if (!window.isSecureContext || !navigator.mediaDevices) throw new Error('Use localhost or trusted HTTPS for camera access');
    const urls = $('urls').value.split(/\s+/).filter(Boolean);
    if (urls.some((url) => !/^turns?:[^\s]+$/.test(url))) throw new Error('Use turn: or turns: URLs only');
    if (urls.length && (!$('username').value || !$('credential').value)) throw new Error('Enter expiring TURN credentials');
    if ($('relay').checked && !urls.length) throw new Error('Forced relay requires TURN settings');
    const acquired = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    if (attempt !== generation) { acquired.getTracks().forEach((track) => track.stop()); return; }
    stream = acquired;
    $('local').srcObject = stream;
    events = [];
    evidence = { schema: 'x01-v1', startedAt: new Date().toISOString(),
      networkLabel: $('network').value, userAgent: navigator.userAgent,
      iceTransportPolicy: $('relay').checked ? 'relay' : 'all',
      turnConfigured: urls.length > 0, calls: [], samples: [] };
    $('stats').textContent = 'Waiting for a call';
    $('mic').textContent = 'Mute microphone';
    $('camera').textContent = 'Disable camera';
    peer = new Peer({ host: location.hostname, port: Number(location.port) || (location.protocol === 'https:' ? 443 : 80),
      secure: location.protocol === 'https:', path: '/peerjs', key: 'x01', debug: 0,
      config: { iceServers: urls.length ? [{ urls, username: $('username').value, credential: $('credential').value }] : [],
        iceTransportPolicy: evidence.iceTransportPolicy } });
    // Credentials stay only in the active RTC configuration, not the evidence or DOM.
    $('credential').value = '';
    peer.on('open', (id) => { $('peer-id').textContent = id; status('Ready'); controls(); });
    peer.on('call', (incoming) => {
      if (call || !stream) { incoming.close(); log('Rejected extra incoming call'); return; }
      status('Answering incoming call');
      attachCall(incoming);
      incoming.answer(stream);
    });
    peer.on('disconnected', () => { status('Signalling disconnected; Leave and Start to reconnect'); controls(); });
    peer.on('error', (error) => {
      if (error.type === 'peer-unavailable') { endCall(); status('Peer unavailable; check the other ID'); }
      else { leave(); status(`Signalling error: ${error.type || 'unknown'}; Start to retry`); }
    });
    status('Connecting to self-hosted signalling');
  } catch (error) {
    if (attempt === generation) { leave(); status(error.message); }
  } finally {
    if (attempt === generation) { starting = false; controls(); }
  }
};
$('call').onclick = () => {
  const id = $('remote-id').value.trim();
  if (!id || id === peer?.id) { status('Enter the other tester’s peer ID'); return; }
  try { attachCall(peer.call(id, stream)); status('Calling'); }
  catch { endCall(); status('Could not start call'); }
};
$('hangup').onclick = () => { endCall(); status('Call ended'); };
$('leave').onclick = leave;
for (const [id, kind, off, on] of [
  ['mic', 'audio', 'Unmute microphone', 'Mute microphone'],
  ['camera', 'video', 'Enable camera', 'Disable camera'],
]) $(id).onclick = () => {
  const tracks = stream?.getTracks().filter((track) => track.kind === kind) || [];
  const enabled = !tracks[0]?.enabled;
  tracks.forEach((track) => { track.enabled = enabled; });
  $(id).textContent = enabled ? on : off;
  log(`${kind} ${enabled ? 'enabled' : 'disabled'}`);
};
$('export').onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify({ ...evidence, events,
    exportedAt: new Date().toISOString() }, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `x01-${Date.now()}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener('beforeunload', leave);
