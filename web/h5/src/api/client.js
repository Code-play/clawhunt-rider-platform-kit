/**
 * 统一 API 层：
 * - 未设置 VITE_API_BASE：走内置 mock（src/mock），700ms 延迟
 * - 已设置 VITE_API_BASE：走真后端 fetch；网络错误 / 5xx 时回落 mock 并打控制台警告（不白屏）
 * - 断网（真实离线或演示开关）：抛 NetworkError，由聊天页做本地排队 + 幂等重放
 */
import { mockRequest } from '../mock/index.js';

const RAW_BASE = (import.meta.env.VITE_API_BASE || '').trim();
export const API_BASE = RAW_BASE.replace(/\/+$/, '');
export const API_MODE = API_BASE ? 'remote' : 'mock';

let offlineSimulated = false;
/** 一旦真后端出现「接口缺失(404)/网络错误/5xx」，本轮会话整体回落 mock，避免真/假数据混用。 */
let stickyMock = false;

export function setSimulatedOffline(value) {
  offlineSimulated = Boolean(value);
  window.dispatchEvent(new CustomEvent('rider:netchange', { detail: { offline: isOffline() } }));
}

export function isSimulatedOffline() {
  return offlineSimulated;
}

export function isOffline() {
  if (offlineSimulated) return true;
  try {
    return typeof navigator !== 'undefined' && navigator.onLine === false;
  } catch {
    return false;
  }
}

export class NetworkError extends Error {
  constructor(message = '网络连接不可用') {
    super(message);
    this.name = 'NetworkError';
    this.code = 'NETWORK_ERROR';
  }
}

export class ApiError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function realRequest(method, path, body, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(window.__riderToken ? { Authorization: `Bearer ${window.__riderToken}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await res.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
    }
    if (!res.ok) {
      throw new ApiError(
        (data && data.code) || `HTTP_${res.status}`,
        (data && data.message) || `请求失败（HTTP ${res.status}）`,
        res.status,
      );
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export async function request(method, path, body) {
  if (isOffline()) throw new NetworkError('当前网络不可用');
  if (!API_BASE || stickyMock) return mockRequest(method, path, body);
  try {
    return await realRequest(method, path, body);
  } catch (err) {
    // 4xx 业务错误（如 422 缺字段）原样抛给页面；404 视为后端未实现该契约接口 → 整体回落。
    if (err instanceof ApiError && err.status < 500 && err.status !== 404) throw err;
    stickyMock = true;
    console.warn(
      `[api] 真后端不可用或与契约不一致（${err.message}），本轮会话整体回落到内置 mock。VITE_API_BASE=${API_BASE}`,
    );
    return mockRequest(method, path, body);
  }
}

/* ---------------- 业务 API（契约 v1） ---------------- */

export function saveConsent(payload) {
  return request('POST', '/api/v1/consent', payload);
}

export function createSession(candidateId) {
  return request('POST', '/api/v1/agent/sessions', { candidate_id: candidateId });
}

export function sendAgentMessage(sessionId, { text, clientMessageId }) {
  return request('POST', `/api/v1/agent/sessions/${sessionId}/messages`, {
    text,
    client_message_id: clientMessageId,
  });
}

export function getCandidate(candidateId) {
  return request('GET', `/api/v1/candidates/${candidateId}`);
}

export function patchCandidate(candidateId, patch) {
  return request('PATCH', `/api/v1/candidates/${candidateId}`, patch);
}

export function listStations() {
  return request('GET', '/api/v1/stations');
}

export function getStation(stationId) {
  return request('GET', `/api/v1/stations/${stationId}`);
}

export function createBooking(payload) {
  return request('POST', '/api/v1/bookings', payload);
}

export function getBooking(bookingId) {
  return request('GET', `/api/v1/bookings/${bookingId}`);
}

export function rescheduleBooking(bookingId, slotStart) {
  return request('PATCH', `/api/v1/bookings/${bookingId}`, { slot_start: slotStart });
}

export function cancelBooking(bookingId) {
  return request('POST', `/api/v1/bookings/${bookingId}/cancel`, {});
}

export function exportMyInfo(candidateId) {
  return request('GET', `/api/v1/candidates/${candidateId}/export`);
}

export function revokeMyInfo(candidateId) {
  return request('POST', `/api/v1/candidates/${candidateId}/revoke`, {});
}
