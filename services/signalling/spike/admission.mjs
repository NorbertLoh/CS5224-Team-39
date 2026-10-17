import { randomBytes, randomUUID } from 'node:crypto';

// In-memory feasibility model only. V02 must supply trusted service context.
export function createAdmissions(appointments, { ttlSeconds = 60, now = Date.now } = {}) {
  if (!Number.isInteger(ttlSeconds) || ttlSeconds < 1 || ttlSeconds > 300) {
    throw new Error('Admission lifetime must be 1-300 seconds');
  }
  const grants = new Map();
  const active = new Map();
  const eligible = (grant) => {
    const appointment = appointments.get(grant.appointmentId);
    return appointment && appointment.payment === 'paid' && appointment.status === 'booked'
      && appointment.participants.includes(grant.subject)
      && now() >= appointment.joinFrom && now() < appointment.joinUntil;
  };
  const live = (grant) => eligible(grant) && now() < grant.expiresAt;
  const slotTaken = (grant) => [...active.values()].some((entry) =>
    entry.appointmentId === grant.appointmentId && entry.subject === grant.subject);
  return {
    issue(subject, appointmentId) {
      // Bound retained state, including unused grants, to this small spike.
      for (const [token, grant] of grants) if (!live(grant)) grants.delete(token);
      const grant = { subject, appointmentId, peerId: randomUUID() };
      if (!eligible(grant) || slotTaken(grant) || grants.size >= 100) throw new Error('Admission denied');
      grant.expiresAt = Math.min(now() + ttlSeconds * 1000, appointments.get(appointmentId).joinUntil);
      const token = randomBytes(32).toString('base64url');
      grants.set(token, grant);
      return { ...grant, token };
    },
    consume(token, peerId) {
      const grant = grants.get(token);
      if (!grant || grant.peerId !== peerId || !live(grant) || slotTaken(grant)) {
        throw new Error('Admission denied');
      }
      grants.delete(token); // Atomic single-use reservation before PeerServer sees the socket.
      active.set(peerId, grant);
      return grant;
    },
    release(grant) {
      if (active.get(grant.peerId) === grant) active.delete(grant.peerId);
    },
    remaining(grant) { return Math.max(0, grant.expiresAt - now()); },
    allows(grant, message) {
      if (!live(grant) || active.get(grant.peerId) !== grant || !message
        || typeof message !== 'object' || Array.isArray(message)
        || (message.src !== undefined && message.src !== grant.peerId)) return false;
      if (message.type === 'HEARTBEAT') return message.dst === undefined;
      if (!['OFFER', 'ANSWER', 'CANDIDATE', 'LEAVE', 'EXPIRE'].includes(message.type)) return false;
      const target = active.get(message.dst);
      return Boolean(target && target !== grant && live(target)
        && target.appointmentId === grant.appointmentId && target.subject !== grant.subject);
    },
  };
}
