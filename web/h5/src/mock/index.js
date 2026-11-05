/**
 * H5 端内置 mock 后端：内存数据 + 700ms 延迟，接口形状与契约 v1 对齐。
 * - 会话 / 7 槽位进度 / 站点 / 预约 / 保险箱令牌化 / 撤回删除
 * - 站点与时段按运行当天生成，隔天打开仍有档期
 * 设置 VITE_API_BASE 后前端会优先请求真后端；本文件只在未配置或后端不可用时生效。
 */
import { buildStations, CONSENT_VERSION, POLICY_DOCS } from './data.js';
import { createSessionState, buildGreeting, handleMessage } from './conversation.js';
import { maskName, maskPhone } from '../lib/format.js';

const LATENCY = Number(
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_MOCK_LATENCY) || 700,
);

const db = {
  candidates: new Map(),
  sessions: new Map(),
  bookings: new Map(),
  stations: buildStations(),
  revoked: new Set(),
};

/**
 * mock 内存库持久化到 localStorage：刷新页面 / 断网恢复后，会话、进度、预约仍然存在。
 * 演示数据只含令牌与掩码，不含完整敏感值；撤回授权时会随 rider.h5.* 一起清空。
 */
const DB_KEY = 'rider.h5.mockdb';

function loadDb() {
  try {
    const raw = window.localStorage.getItem(DB_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    const today = new Date().toISOString().slice(0, 10);
    db.candidates = new Map(data.candidates || []);
    db.sessions = new Map(data.sessions || []);
    db.bookings = new Map(data.bookings || []);
    db.revoked = new Set(data.revoked || []);
    // 站点时段按天生成：跨天后重新生成，避免出现过期档期。
    db.stations =
      data.built_on === today && Array.isArray(data.stations) && data.stations.length
        ? data.stations
        : buildStations();
  } catch (err) {
    console.warn('[mock] 本地 mock 数据恢复失败，使用全新数据:', err);
  }
}

function persistDb() {
  try {
    window.localStorage.setItem(
      DB_KEY,
      JSON.stringify({
        built_on: new Date().toISOString().slice(0, 10),
        candidates: [...db.candidates.entries()],
        sessions: [...db.sessions.entries()],
        bookings: [...db.bookings.entries()],
        stations: db.stations,
        revoked: [...db.revoked],
      }),
    );
  } catch (err) {
    console.warn('[mock] 本地 mock 数据持久化失败:', err);
  }
}

loadDb();

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function apiError(code, message, status = 400) {
  const err = new Error(message);
  err.code = code;
  err.status = status;
  return err;
}

function newId(prefix) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function tokenize(type, value) {
  let hash = 0;
  const raw = `${type}:${value}:${Date.now()}`;
  for (let i = 0; i < raw.length; i += 1) hash = (hash * 31 + raw.charCodeAt(i)) >>> 0;
  return `tok_${type}_${hash.toString(36)}`;
}

function publicCandidate(candidate) {
  return {
    id: candidate.id,
    name_token: candidate.name_token,
    name_masked: candidate.name_masked,
    phone_token: candidate.phone_token,
    phone_masked: candidate.phone_masked,
    birth_ym: candidate.birth_ym,
    area_text: candidate.area_text,
    job_type: candidate.job_type,
    has_ebike: candidate.has_ebike,
    start_text: candidate.start_text,
    experience_text: candidate.experience_text,
    health_cert: candidate.health_cert,
    source_channel: candidate.source_channel,
    station_id: candidate.station_id,
    status: candidate.status,
    consent_version: candidate.consent_version,
    consent_at: candidate.consent_at,
    updated_at: candidate.updated_at,
  };
}

function publicStation(station, { withSlots = true } = {}) {
  const activeBookings = [...db.bookings.values()].filter(
    (b) => b.station_id === station.id && b.status === 'booked',
  );
  return {
    id: station.id,
    name: station.name,
    address: station.address,
    area: station.area,
    lat: station.lat,
    lng: station.lng,
    distance_km: station.distance_km,
    open_quota: station.open_quota,
    booked_count: activeBookings.length,
    manager_virtual_no: station.manager_virtual_no,
    manager_display_no: station.manager_display_no,
    ...(withSlots ? { slots: station.slots.map((s) => ({ ...s })) } : {}),
  };
}

function publicBooking(booking) {
  const station = db.stations.find((s) => s.id === booking.station_id);
  return {
    ...booking,
    station: station ? publicStation(station, { withSlots: false }) : null,
  };
}

function getCandidate(id) {
  const candidate = db.candidates.get(id);
  if (!candidate) throw apiError('CANDIDATE_NOT_FOUND', '候选人不存在或已删除', 404);
  return candidate;
}

function findSlot(station, slotStart) {
  const slot = station.slots.find((s) => s.slot_start === slotStart);
  if (!slot) throw apiError('SLOT_NOT_FOUND', '时段不存在，请刷新后重试', 404);
  if (!slot.available) throw apiError('SLOT_FULL', '该时段已约满，请选择其他时段', 409);
  return slot;
}

function handleSaveConsent(body) {
  const { consent_version, consent_at, source_channel, candidate_id } = body || {};
  if (!consent_version || !consent_at) {
    throw apiError('CONSENT_REQUIRED', '缺少 consent_version 或 consent_at', 422);
  }
  let candidate = candidate_id ? db.candidates.get(candidate_id) : null;
  if (candidate) {
    candidate.consent_version = consent_version;
    candidate.consent_at = consent_at;
    candidate.source_channel = source_channel || candidate.source_channel;
    candidate.updated_at = nowIso();
  } else {
    candidate = {
      id: newId('cand'),
      name_token: null,
      name_masked: null,
      phone_token: null,
      phone_masked: null,
      birth_ym: null,
      area_text: null,
      job_type: null,
      has_ebike: null,
      start_text: null,
      experience_text: null,
      health_cert: null,
      source_channel: source_channel || 'direct',
      station_id: null,
      status: 'collecting',
      consent_version,
      consent_at,
      created_at: nowIso(),
      updated_at: nowIso(),
    };
    db.candidates.set(candidate.id, candidate);
  }
  return {
    candidate_id: candidate.id,
    consent_version: candidate.consent_version,
    consent_at: candidate.consent_at,
    consent_doc: { version: CONSENT_VERSION },
  };
}

function handleCreateSession(body) {
  const { candidate_id } = body || {};
  const candidate = getCandidate(candidate_id);
  const session = createSessionState(candidate.id);
  db.sessions.set(session.id, session);
  return {
    session_id: session.id,
    candidate_id: candidate.id,
    greeting: buildGreeting(session),
  };
}

function handleMessageRoute(sessionId, body) {
  const session = db.sessions.get(sessionId);
  if (!session) throw apiError('SESSION_NOT_FOUND', '会话不存在或已过期', 404);
  const candidate = getCandidate(session.candidate_id);
  const clientMessageId = body && body.client_message_id;
  // 幂等：同一个客户端消息 id 重复提交（断网重放）直接返回首次结果，不重复推进槽位。
  if (clientMessageId && session.replied[clientMessageId]) {
    return { ...session.replied[clientMessageId], replayed: true };
  }
  const result = handleMessage({
    session,
    candidate,
    text: body && body.text,
    stations: db.stations.map((s) => ({
      ...s,
      slots: s.slots.map((slot) => ({ ...slot })),
    })),
  });
  const payload = {
    ...result,
    message_id: newId('msg'),
    candidate_id: candidate.id,
  };
  if (clientMessageId) session.replied[clientMessageId] = payload;
  return payload;
}

function handleCreateBooking(body) {
  const { candidate_id, station_id, slot_start } = body || {};
  const candidate = getCandidate(candidate_id);
  const station = db.stations.find((s) => s.id === station_id);
  if (!station) throw apiError('STATION_NOT_FOUND', '站点不存在', 404);
  const slot = findSlot(station, slot_start);
  slot.booked += 1;
  slot.available = slot.booked < slot.capacity;
  const booking = {
    id: newId('bk'),
    candidate_id,
    station_id,
    slot_start,
    slot_label: slot_start,
    status: 'booked',
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  db.bookings.set(booking.id, booking);
  candidate.station_id = station_id;
  candidate.status = 'booked';
  candidate.updated_at = nowIso();
  return { ...publicBooking(booking), arrival_notice: undefined };
}

function handleReschedule(bookingId, body) {
  const booking = db.bookings.get(bookingId);
  if (!booking) throw apiError('BOOKING_NOT_FOUND', '预约不存在', 404);
  if (booking.status !== 'booked') throw apiError('BOOKING_STATUS_INVALID', '当前预约状态不支持改约', 409);
  const station = db.stations.find((s) => s.id === booking.station_id);
  const oldSlot = station.slots.find((s) => s.slot_start === booking.slot_start);
  const nextSlot = findSlot(station, body && body.slot_start);
  if (oldSlot) {
    oldSlot.booked = Math.max(0, oldSlot.booked - 1);
    oldSlot.available = oldSlot.booked < oldSlot.capacity;
  }
  nextSlot.booked += 1;
  nextSlot.available = nextSlot.booked < nextSlot.capacity;
  booking.slot_start = nextSlot.slot_start;
  booking.updated_at = nowIso();
  return publicBooking(booking);
}

function handleCancelBooking(bookingId) {
  const booking = db.bookings.get(bookingId);
  if (!booking) throw apiError('BOOKING_NOT_FOUND', '预约不存在', 404);
  if (booking.status !== 'booked') throw apiError('BOOKING_STATUS_INVALID', '当前预约状态不支持取消', 409);
  const station = db.stations.find((s) => s.id === booking.station_id);
  const slot = station && station.slots.find((s) => s.slot_start === booking.slot_start);
  if (slot) {
    slot.booked = Math.max(0, slot.booked - 1);
    slot.available = slot.booked < slot.capacity;
  }
  booking.status = 'cancelled';
  booking.updated_at = nowIso();
  const candidate = db.candidates.get(booking.candidate_id);
  if (candidate && candidate.status === 'booked') {
    candidate.status = 'complete';
    candidate.updated_at = nowIso();
  }
  return publicBooking(booking);
}

function handleExport(candidateId) {
  const candidate = getCandidate(candidateId);
  return {
    exported_at: nowIso(),
    candidate: {
      id: candidate.id,
      name: candidate.name_masked,
      phone: candidate.phone_masked,
      birth_ym: candidate.birth_ym,
      area_text: candidate.area_text,
      job_type: candidate.job_type,
      has_ebike: candidate.has_ebike,
      start_text: candidate.start_text,
      source_channel: candidate.source_channel,
      status: candidate.status,
    },
    consent: { version: candidate.consent_version, at: candidate.consent_at },
    note: '姓名与手机号在本副本中仍以掩码展示；需要完整值请通过人工客服核验身份后获取。',
  };
}

function handleRevoke(candidateId) {
  const candidate = db.candidates.get(candidateId);
  if (!candidate) throw apiError('CANDIDATE_NOT_FOUND', '候选人不存在或已删除', 404);
  const bookings = [...db.bookings.values()].filter((b) => b.candidate_id === candidateId);
  bookings.forEach((b) => {
    const station = db.stations.find((s) => s.id === b.station_id);
    const slot = station && station.slots.find((s) => s.slot_start === b.slot_start);
    if (slot && b.status === 'booked') {
      slot.booked = Math.max(0, slot.booked - 1);
      slot.available = slot.booked < slot.capacity;
    }
    db.bookings.delete(b.id);
  });
  [...db.sessions.values()]
    .filter((s) => s.candidate_id === candidateId)
    .forEach((s) => db.sessions.delete(s.id));
  db.candidates.delete(candidateId);
  db.revoked.add(candidateId);
  return { deleted: true, candidate_id: candidateId, deleted_at: nowIso() };
}

/** 路由表：与契约 v1 对齐；个别应答字段（name_masked/phone_masked、greeting、stations）为前端演示所需扩展。 */
async function routeMock(method, path, body = {}) {
  await delay(LATENCY);
  const url = new URL(path, 'http://mock.local');
  const pathname = url.pathname.replace(/\/+$/, '');
  const m = method.toUpperCase();

  if (m === 'POST' && pathname === '/api/v1/consent') return handleSaveConsent(body);

  if (m === 'POST' && pathname === '/api/v1/agent/sessions') return handleCreateSession(body);

  let match = pathname.match(/^\/api\/v1\/agent\/sessions\/([^/]+)\/messages$/);
  if (m === 'POST' && match) return handleMessageRoute(match[1], body);

  if (m === 'GET' && pathname === '/api/v1/stations') {
    return { stations: db.stations.map((s) => publicStation(s)) };
  }

  match = pathname.match(/^\/api\/v1\/stations\/([^/]+)$/);
  if (m === 'GET' && match) {
    const station = db.stations.find((s) => s.id === match[1]);
    if (!station) throw apiError('STATION_NOT_FOUND', '站点不存在', 404);
    return publicStation(station);
  }

  if (m === 'POST' && pathname === '/api/v1/bookings') return handleCreateBooking(body);

  match = pathname.match(/^\/api\/v1\/bookings\/([^/]+)\/cancel$/);
  if (m === 'POST' && match) return handleCancelBooking(match[1]);

  match = pathname.match(/^\/api\/v1\/bookings\/([^/]+)$/);
  if (match) {
    const booking = db.bookings.get(match[1]);
    if (!booking) throw apiError('BOOKING_NOT_FOUND', '预约不存在', 404);
    if (m === 'GET') return publicBooking(booking);
    if (m === 'PATCH') return handleReschedule(match[1], body);
  }

  match = pathname.match(/^\/api\/v1\/candidates\/([^/]+)\/export$/);
  if (m === 'GET' && match) return handleExport(match[1]);

  match = pathname.match(/^\/api\/v1\/candidates\/([^/]+)\/revoke$/);
  if (m === 'POST' && match) return handleRevoke(match[1]);

  match = pathname.match(/^\/api\/v1\/candidates\/([^/]+)$/);
  if (match) {
    const candidate = getCandidate(match[1]);
    if (m === 'GET') return publicCandidate(candidate);
    if (m === 'PATCH') {
      const allowed = [
        'name',
        'phone',
        'birth_ym',
        'area_text',
        'job_type',
        'has_ebike',
        'start_text',
        'experience_text',
        'health_cert',
      ];
      allowed.forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(body, key)) {
          if (key === 'name') {
            candidate.name_token = tokenize('name', body.name);
            candidate.name_masked = maskName(body.name);
          } else if (key === 'phone') {
            candidate.phone_token = tokenize('phone', body.phone);
            candidate.phone_masked = maskPhone(body.phone);
          } else {
            candidate[key] = body[key];
          }
        }
      });
      candidate.updated_at = nowIso();
      return publicCandidate(candidate);
    }
  }

  if (m === 'POST' && pathname === '/api/v1/vault/tokenize') {
    if (!body || !body.type || !body.value) {
      throw apiError('INVALID_ARGUMENT', '缺少 type 或 value', 422);
    }
    return { token: tokenize(body.type, body.value), type: body.type };
  }

  if (m === 'GET' && pathname === '/api/v1/policy/docs') {
    return { docs: Object.values(POLICY_DOCS) };
  }

  throw apiError('NOT_FOUND', `mock 未实现该接口: ${m} ${pathname}`, 404);
}

/** 对外入口：先走路由，再把内存库落盘，保证刷新/断网恢复后会话与进度可恢复。 */
export async function mockRequest(method, path, body = {}) {
  const result = await routeMock(method, path, body);
  persistDb();
  return result;
}

/** 演示用：重置内存数据与本地持久化。 */
export function resetMockDb() {
  db.candidates.clear();
  db.sessions.clear();
  db.bookings.clear();
  db.revoked.clear();
  db.stations = buildStations();
  try {
    window.localStorage.removeItem(DB_KEY);
  } catch {
    /* ignore */
  }
}
