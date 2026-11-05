/**
 * 管理端统一 API 层：
 * - 未设置 VITE_API_BASE：走内置 mock（src/mock），700ms 延迟
 * - 已设置 VITE_API_BASE：走真后端 fetch，带 Bearer JWT；网络错误/5xx 回落 mock 并警告
 * - 4xx 业务错误（未登录、缺理由等）直接抛给页面处理，不回落
 */
import { mockRequest } from '../mock/index.js';

const RAW_BASE = (import.meta.env.VITE_API_BASE || '').trim();
export const API_BASE = RAW_BASE.replace(/\/+$/, '');
export const API_MODE = API_BASE ? 'remote' : 'mock';

let authToken = '';
/** 真后端接口缺失(404)/网络错误/5xx 时整体回落 mock，避免真/假数据混用。 */
let stickyMock = false;

export function setAuthToken(token) {
  authToken = token || '';
  if (typeof window !== 'undefined') window.__adminToken = authToken;
}

export function getAuthToken() {
  return authToken;
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

async function realRequest(method, path, body, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
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
  if (!API_BASE || stickyMock) return mockRequest(method, path, body);
  try {
    return await realRequest(method, path, body);
  } catch (err) {
    // 4xx 业务错误（未登录、缺理由等）交给页面处理；404 视为后端未实现契约接口 → 整体回落。
    if (err instanceof ApiError && err.status < 500 && err.status !== 404) throw err;
    stickyMock = true;
    console.warn(
      `[admin api] 真后端不可用或与契约不一致（${err.message}），本轮会话整体回落到内置 mock。VITE_API_BASE=${API_BASE}`,
    );
    return mockRequest(method, path, body);
  }
}

/* ---------------- 业务 API ---------------- */

export function login(payload) {
  return request('POST', '/api/v1/auth/login', payload);
}

function toQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.append(key, value);
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function listCandidates(params) {
  return request('GET', `/api/v1/admin/candidates${toQuery(params)}`);
}

export function getCandidate(candidateId) {
  return request('GET', `/api/v1/admin/candidates/${candidateId}`);
}

export function patchCandidate(candidateId, payload) {
  return request('PATCH', `/api/v1/admin/candidates/${candidateId}`, payload);
}

export function runCandidateAction(candidateId, payload) {
  return request('POST', `/api/v1/admin/candidates/${candidateId}/actions`, payload);
}

export function listInterviews(params) {
  return request('GET', `/api/v1/admin/interviews${toQuery(params)}`);
}

export function listStations() {
  return request('GET', '/api/v1/admin/stations');
}

export function updateStationQuota(stationId, openQuota) {
  return request('PATCH', `/api/v1/admin/stations/${stationId}`, { open_quota: openQuota });
}

export function getMetrics() {
  return request('GET', '/api/v1/admin/metrics');
}

export function detokenize(token, reason) {
  return request('POST', '/api/v1/vault/detokenize', { token, reason });
}

export function tokenize(type, value) {
  return request('POST', '/api/v1/vault/tokenize', { type, value });
}

export function listDetokenizeLogs() {
  return request('GET', '/api/v1/admin/audit/detokenize');
}
