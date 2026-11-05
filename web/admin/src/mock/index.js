/**
 * 管理端内置 mock：内存数据 + 700ms 延迟，接口形状与契约 v1 对齐。
 * 注意：管理端 mock 数据不落 localStorage（刷新即恢复演示初始数据），
 * 完整手机号/姓名仅存在于本模块内存的 vault 中，查看需理由并写审计。
 * 设置 VITE_API_BASE 后前端优先请求真后端，不可用时回落本 mock。
 */
import dayjs from 'dayjs';
import { maskName, maskPhone, JOB_TYPE_LABEL, HEALTH_LABEL, FIELD_LABELS } from '../lib/utils.js';

const LATENCY = Number(
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_MOCK_LATENCY) || 700,
);

const EMPLOYEE = {
  name: '张敏',
  employee_no: 'A1024',
  role: '招聘专员',
  station: '张江高科站',
};

const STATION_DEFS = [
  {
    id: 'st_zhangjiang',
    name: '张江高科站',
    area: '浦东新区',
    address: '浦东新区张江路 88 号',
    open_quota: 12,
    booked: 7,
    today_visits: 4,
    manager: '李建国',
  },
  {
    id: 'st_shijigongyuan',
    name: '世纪公园站',
    area: '浦东新区',
    address: '浦东新区锦绣路 1001 号',
    open_quota: 8,
    booked: 6,
    today_visits: 3,
    manager: '王芳',
  },
  {
    id: 'st_jinqiao',
    name: '金桥站',
    area: '浦东新区',
    address: '浦东新区金桥路 1388 号',
    open_quota: 5,
    booked: 5,
    today_visits: 1,
    manager: '赵强',
  },
  {
    id: 'st_lujiazui',
    name: '陆家嘴站',
    area: '浦东新区',
    address: '浦东新区浦东南路 500 号',
    open_quota: 3,
    booked: 1,
    today_visits: 1,
    manager: '陈晨',
  },
  {
    id: 'st_chuansha',
    name: '川沙站',
    area: '浦东新区',
    address: '浦东新区川环南路 200 号',
    open_quota: 6,
    booked: 2,
    today_visits: 2,
    manager: '周涛',
  },
  {
    id: 'st_huinan',
    name: '惠南站',
    area: '浦东新区',
    address: '浦东新区人民东路 66 号',
    open_quota: 4,
    booked: 4,
    today_visits: 0,
    manager: '孙立',
  },
];

const RAW_CANDIDATES = [
  {
    name: '王伟',
    phone: '13800138001',
    birth_ym: '1996-03',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '明天',
    experience_text: '2 年外卖配送经验',
    health_cert: 'yes',
    source_channel: 'douyin',
    station_id: 'st_zhangjiang',
    status: 'booked',
    intent_level: 5,
    created_days_ago: 0,
    summary: '求职意向明确：全职跑单、有 2 年配送经验，已预约张江高科站面试。对保险与结算规则关注度高。',
    key_points: ['全职、可次日到岗', '自有电动车，持健康证', '住张江，距站点约 1.2km'],
  },
  {
    name: '李娜',
    phone: '13800138002',
    birth_ym: '1999-11',
    area_text: '浦东新区',
    job_type: 'parttime',
    has_ebike: false,
    start_text: '本周内',
    experience_text: '无配送经验，做过门店导购',
    health_cert: 'no',
    source_channel: 'wechat',
    station_id: 'st_shijigongyuan',
    status: 'complete',
    intent_level: 3,
    created_days_ago: 1,
    summary: '想做周末兼职，暂无电动车，需确认租车方案；健康证待办理。',
    key_points: ['兼职、周末为主', '需要租车支持', '健康证未办理'],
  },
  {
    name: '刘洋',
    phone: '13800138003',
    birth_ym: '1993-07',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '下个月',
    experience_text: '3 年同城配送经验',
    health_cert: 'yes',
    source_channel: 'moments',
    station_id: 'st_jinqiao',
    status: 'booked',
    intent_level: 4,
    created_days_ago: 2,
    summary: '资深配送骑手，计划下月从原平台转来，已预约金桥站面试。',
    key_points: ['3 年经验', '下月到岗', '关注单价与补贴'],
  },
  {
    name: '陈静',
    phone: '13800138004',
    birth_ym: '2000-02',
    area_text: '浦东新区',
    job_type: 'parttime',
    has_ebike: true,
    start_text: '明天',
    experience_text: '1 年奶茶店兼职',
    health_cert: 'yes',
    source_channel: 'offline_poster',
    station_id: 'st_shijigongyuan',
    status: 'interviewed',
    intent_level: 4,
    created_days_ago: 3,
    summary: '兼职意向，已到世纪公园站完成面试，等待站点确认排班。',
    key_points: ['兼职、可立即到岗', '有电动车与健康证', '面试已到访'],
  },
  {
    name: '杨帆',
    phone: '13800138005',
    birth_ym: '1991-09',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: false,
    start_text: '本周内',
    experience_text: '5 年快递配送经验',
    health_cert: 'unsure',
    source_channel: 'referral',
    station_id: 'st_lujiazui',
    status: 'complete',
    intent_level: 5,
    created_days_ago: 4,
    summary: '老骑手推荐，5 年快递经验，可本周到岗；健康证情况待确认。',
    key_points: ['老骑手推荐', '5 年配送经验', '健康证待确认'],
  },
  {
    name: '赵雷',
    phone: '13800138006',
    birth_ym: '2002-12',
    area_text: '浦东新区',
    job_type: 'undecided',
    has_ebike: false,
    start_text: '随时',
    experience_text: '无经验',
    health_cert: 'unsure',
    source_channel: 'douyin',
    station_id: null,
    status: 'new',
    intent_level: 2,
    created_days_ago: 0,
    summary: '刚留资，工作类型未定，尚未完成对话采集。',
    key_points: ['刚留资', '无配送经验', '工作类型未定'],
  },
  {
    name: '孙悦',
    phone: '13800138007',
    birth_ym: '1998-05',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '明天',
    experience_text: '1 年外卖配送经验',
    health_cert: 'yes',
    source_channel: 'wechat',
    station_id: 'st_zhangjiang',
    status: 'handoff',
    intent_level: 4,
    created_days_ago: 5,
    summary: '候选人要求人工确认排班与住宿问题，已转人工跟进。',
    key_points: ['已转人工', '关注住宿', '可次日到岗'],
  },
  {
    name: '周杰',
    phone: '13800138008',
    birth_ym: '1994-08',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '已到岗',
    experience_text: '4 年配送经验',
    health_cert: 'yes',
    source_channel: 'referral',
    station_id: 'st_chuansha',
    status: 'hired',
    intent_level: 5,
    created_days_ago: 6,
    summary: '已入职川沙站，首周跟车试跑中。',
    key_points: ['已入职', '4 年经验', '老骑手推荐'],
  },
  {
    name: '吴桐',
    phone: '13800138009',
    birth_ym: '2001-06',
    area_text: '浦东新区',
    job_type: 'parttime',
    has_ebike: true,
    start_text: '本周内',
    experience_text: '学生兼职，无配送经验',
    health_cert: 'no',
    source_channel: 'offline_poster',
    station_id: null,
    status: 'collecting',
    intent_level: 2,
    created_days_ago: 0,
    summary: '在校学生找周末兼职，对话进行到工作类型，健康证未办理。',
    key_points: ['学生兼职', '仅周末可到岗', '健康证未办理'],
  },
  {
    name: '郑爽',
    phone: '13800138010',
    birth_ym: '1988-04',
    area_text: '闵行区',
    job_type: 'fulltime',
    has_ebike: false,
    start_text: '三个月后',
    experience_text: '无经验',
    health_cert: 'no',
    source_channel: 'douyin',
    station_id: 'st_lujiazui',
    status: 'rejected',
    intent_level: 1,
    created_days_ago: 7,
    summary: '住闵行、三个月后才能到岗，与在招站点通勤距离过远，标记不合适。',
    key_points: ['区域不匹配', '到岗时间过晚', '无配送经验'],
  },
  {
    name: '何勇',
    phone: '13800138011',
    birth_ym: '1997-10',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '明天',
    experience_text: '2 年商超配送经验',
    health_cert: 'yes',
    source_channel: 'moments',
    station_id: 'st_zhangjiang',
    status: 'complete',
    intent_level: 5,
    created_days_ago: 1,
    summary: '资料完整，全职可次日到岗，等待专员确认面试时间。',
    key_points: ['全职、次日到岗', '2 年商超配送', '住张江'],
  },
  {
    name: '马超',
    phone: '13800138012',
    birth_ym: '1995-01',
    area_text: '浦东新区',
    job_type: 'fulltime',
    has_ebike: true,
    start_text: '本周内',
    experience_text: '3 年外卖配送经验',
    health_cert: 'yes',
    source_channel: 'wechat',
    station_id: 'st_huinan',
    status: 'booked',
    intent_level: 4,
    created_days_ago: 2,
    summary: '已预约惠南站面试，关注结算周期与租车费用。',
    key_points: ['本周内到岗', '3 年经验', '关注租车费用'],
  },
];

const db = {
  candidates: [],
  stations: [],
  interviews: [],
  vault: new Map(),
  detokenizeLogs: [],
  auditSeq: 0,
};

function apiError(code, message, status = 400) {
  const err = new Error(message);
  err.code = code;
  err.status = status;
  return err;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function newId(prefix) {
  db.auditSeq += 1;
  return `${prefix}_${Date.now().toString(36)}${db.auditSeq.toString(36)}`;
}

function stationById(id) {
  return db.stations.find((s) => s.id === id);
}

function stationName(id) {
  const station = stationById(id);
  return station ? station.name : '-';
}

function fullName(candidate) {
  return db.vault.get(candidate.name_token) || '';
}

function fullPhone(candidate) {
  return db.vault.get(candidate.phone_token) || '';
}

function ageOf(birthYm) {
  if (!birthYm) return null;
  const d = dayjs(`${birthYm}-01`);
  if (!d.isValid()) return null;
  return dayjs().diff(d, 'year');
}

function buildQualification(raw) {
  const age = ageOf(raw.birth_ym);
  const rules = [
    {
      rule: '年龄 18-45 周岁',
      pass: age != null && age >= 18 && age <= 45,
      note: age != null ? `${age} 岁` : '出生年月缺失',
    },
    {
      rule: '有电动车或可租赁',
      pass: Boolean(raw.has_ebike),
      note: raw.has_ebike ? '自有电动车' : '需站点协助租车',
    },
    {
      rule: '7 天内可到岗',
      pass: /明天|本周|今天|随时|立即|已到岗/.test(raw.start_text || ''),
      note: raw.start_text || '未填写',
    },
    {
      rule: '持有效健康证',
      pass: raw.health_cert === 'yes',
      note: HEALTH_LABEL[raw.health_cert] || '待确认',
    },
    {
      rule: '区域与在招站点匹配',
      pass: raw.area_text === '浦东新区',
      note: `${raw.area_text || '-'} · ${stationName(raw.station_id)}`,
    },
    {
      rule: '有配送/跑单经验',
      pass: /年|个月|配送|外卖|快递/.test(raw.experience_text || ''),
      note: raw.experience_text || '无经验',
    },
  ];
  const passed = rules.filter((r) => r.pass).length;
  const base = 52 + passed * 6 + (raw.intent_level || 0) * 2;
  const score = Math.min(98, base);
  const level = score >= 85 ? 'recommend' : score >= 70 ? 'follow' : 'reject';
  return { level, score, rules, suggestion: buildSuggestion(level, rules) };
}

function buildSuggestion(level, rules) {
  const failed = rules.filter((r) => !r.pass);
  if (level === 'recommend') {
    return `建议优先安排面试：${rules.filter((r) => r.pass).length}/6 项条件满足，可当天约站。`;
  }
  if (level === 'follow') {
    return `可跟进：${failed.map((r) => r.rule).join('、') || '部分信息'} 需进一步确认后再约面试。`;
  }
  return `暂不建议约面：${failed.map((r) => r.rule).join('、') || '关键条件不满足'}，建议先电话核实。`;
}

function buildTranscript(raw, created) {
  const t = (minutes) => dayjs(created).add(minutes, 'minute').toISOString();
  return [
    { role: 'ai', text: '你好，我是骑手招募助手，本次登记共 7 项信息，可随时转人工。先问一下，怎么称呼你？', ts: t(0) },
    { role: 'user', text: '你好，我想找骑手工作', ts: t(1) },
    { role: 'ai', text: '收到。请提供手机号、出生年月和跑单区域，我会按距离推荐在招站点。', ts: t(1) },
    {
      role: 'user',
      text: `${raw.area_text}，${JOB_TYPE_LABEL[raw.job_type] || raw.job_type}，${
        raw.has_ebike ? '有电动车' : '没有电动车'
      }，${raw.start_text}能到岗`,
      ts: t(2),
    },
    {
      role: 'ai',
      text: `信息已收齐，为你推荐 ${stationName(raw.station_id)}（在招 8 人，距你约 2.1km）。可选时段：明天 09:00 / 13:30 / 16:00。`,
      ts: t(3),
    },
    { role: 'user', text: '保险怎么算？', ts: t(4) },
    {
      role: 'ai',
      text: '平台为完成实名认证且当日接单的骑手投保当日意外险，接单当日生效、次日零时失效，无需骑手付费。（出处：《骑手合作保障与商业保险说明》v2026.3）',
      ts: t(4),
    },
  ];
}

function buildAuditLog(raw, created, index) {
  const logs = [
    {
      id: `audit_seed_${index}_0`,
      at: dayjs(created).add(3, 'minute').toISOString(),
      operator: 'AI 建档',
      field: '全部字段',
      from: '-',
      to: '对话自动采集',
      reason: 'AI 对话采集自动写入',
    },
  ];
  if (index % 3 === 0) {
    logs.push({
      id: `audit_seed_${index}_1`,
      at: dayjs(created).add(1, 'day').toISOString(),
      operator: '张敏（A1024）',
      field: '跑单区域',
      from: '张江',
      to: raw.area_text,
      reason: '电话沟通后补充到区级',
    });
  }
  if (index === 3) {
    logs.push({
      id: `audit_seed_${index}_2`,
      at: dayjs(created).add(2, 'hour').toISOString(),
      operator: '张敏（A1024）',
      field: '可到岗时间',
      from: '下周',
      to: raw.start_text,
      reason: '候选人更正到岗时间',
    });
  }
  return logs.sort((a, b) => (a.at < b.at ? 1 : -1));
}

const WEEKDAY_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function buildInterviewSlots() {
  const slots = [];
  const times = [
    [9, 0],
    [10, 30],
    [14, 0],
    [15, 30],
    [16, 30],
  ];
  for (let d = 1; d <= 3; d += 1) {
    times.forEach(([hour, minute], i) => {
      const dt = dayjs().add(d, 'day').hour(hour).minute(minute).second(0);
      slots.push({
        slot_start: dt.toISOString(),
        label: `${dt.format('MM-DD')} ${WEEKDAY_CN[dt.day()]} ${dt.format('HH:mm')}`,
        available: (d + i) % 5 !== 0,
      });
    });
  }
  return slots;
}

function buildCandidates() {
  return RAW_CANDIDATES.map((raw, index) => {
    const created = dayjs()
      .subtract(raw.created_days_ago, 'day')
      .hour(9 + (index % 8))
      .minute((index * 7) % 60)
      .second(0);
    const nameToken = `tok_name_${String(index + 1).padStart(3, '0')}`;
    const phoneToken = `tok_phone_${String(index + 1).padStart(3, '0')}`;
    db.vault.set(nameToken, raw.name);
    db.vault.set(phoneToken, raw.phone);
    return {
      id: `cand_${String(index + 1).padStart(4, '0')}`,
      name_token: nameToken,
      name_masked: maskName(raw.name),
      phone_token: phoneToken,
      phone_masked: maskPhone(raw.phone),
      birth_ym: raw.birth_ym,
      area_text: raw.area_text,
      job_type: raw.job_type,
      has_ebike: raw.has_ebike,
      start_text: raw.start_text,
      experience_text: raw.experience_text,
      health_cert: raw.health_cert,
      source_channel: raw.source_channel,
      station_id: raw.station_id,
      station_name: stationName(raw.station_id),
      status: raw.status,
      intent_level: raw.intent_level,
      consent_version: 'v1.2',
      consent_at: created.toISOString(),
      qualification: buildQualification(raw),
      conversation_summary: raw.summary,
      conversation_key_points: raw.key_points,
      transcript: buildTranscript(raw, created),
      audit_log: buildAuditLog(raw, created, index),
      interview_slots: buildInterviewSlots(),
      created_at: created.toISOString(),
      updated_at: created.add(index + 1, 'hour').toISOString(),
    };
  });
}

function buildInterviews(candidates) {
  const weekStart = dayjs().startOf('week').add(1, 'day'); // 周一
  const seeds = [
    [0, 1, 10, 0, 'booked'],
    [2, 1, 14, 0, 'booked'],
    [3, 0, 10, 0, 'done'],
    [7, 2, 16, 30, 'booked'],
    [11, 3, 9, 30, 'booked'],
    [4, 4, 13, 0, 'booked'],
    [9, 0, 15, 0, 'no_show'],
    [1, 5, 11, 0, 'booked'],
  ];
  return seeds.map(([ci, dayOffset, hour, minute, status], i) => {
    const candidate = candidates[ci];
    const dt = weekStart.add(dayOffset, 'day').hour(hour).minute(minute).second(0);
    return {
      id: `itv_${String(i + 1).padStart(3, '0')}`,
      candidate_id: candidate.id,
      candidate_name: candidate.name_masked,
      candidate_phone_masked: candidate.phone_masked,
      station_id: candidate.station_id,
      station_name: candidate.station_name,
      slot_start: dt.toISOString(),
      status,
      note: status === 'done' ? '面试已到访' : status === 'no_show' ? '未到访，待回访' : '待面试',
    };
  });
}

function buildMetrics() {
  return {
    generated_at: nowIso(),
    kpis: [
      { key: 'new_leads', label: '今日新增线索', value: 128, unit: '人', delta: 12.5, trend: [42, 58, 51, 66, 73, 69, 88] },
      { key: 'valid_profiles', label: '有效建档数', value: 96, unit: '人', delta: 8.2, trend: [31, 44, 48, 52, 60, 64, 71] },
      { key: 'complete_rate', label: '建档完成率', value: 75.0, unit: '%', delta: 3.1, trend: [61, 63, 66, 68, 71, 73, 75] },
      { key: 'bookings', label: '本周预约面试', value: 64, unit: '场', delta: 6.0, trend: [8, 11, 9, 14, 12, 15, 13] },
      { key: 'visit_rate', label: '预约到访率', value: 82.0, unit: '%', delta: 1.8, trend: [76, 78, 79, 80, 79, 81, 82] },
      { key: 'hired', label: '本月入职转化', value: 38, unit: '人', delta: -2.4, trend: [9, 7, 8, 6, 5, 4, 3] },
      { key: 'avg_reply', label: 'AI 平均首响', value: 42, unit: '秒', delta: -8.0, trend: [61, 58, 55, 51, 47, 45, 42] },
    ],
    funnel: [
      { label: '线索留资', value: 1280 },
      { label: '有效建档', value: 960 },
      { label: '预约面试', value: 640 },
      { label: '到站面试', value: 525 },
      { label: '入职', value: 380 },
    ],
    channels: [
      { name: '抖音短视频', value: 420 },
      { name: '微信好友', value: 360 },
      { name: '朋友圈广告', value: 260 },
      { name: '线下海报', value: 150 },
      { name: '老骑手推荐', value: 90 },
    ],
  };
}

function bootstrap() {
  db.stations = STATION_DEFS.map((def) => {
    const remaining = Math.max(0, def.open_quota - def.booked);
    return {
      ...def,
      remaining,
      status: remaining > 0 ? 'active' : 'full',
    };
  });
  db.candidates = buildCandidates();
  db.interviews = buildInterviews(db.candidates);
  db.metrics = buildMetrics();
}

bootstrap();

/* ------------------------- 序列化 ------------------------- */

function serializeCandidate(candidate, { withDetail = false } = {}) {
  const base = {
    id: candidate.id,
    name_masked: candidate.name_masked,
    phone_masked: candidate.phone_masked,
    name_token: candidate.name_token,
    phone_token: candidate.phone_token,
    birth_ym: candidate.birth_ym,
    area_text: candidate.area_text,
    job_type: candidate.job_type,
    has_ebike: candidate.has_ebike,
    start_text: candidate.start_text,
    experience_text: candidate.experience_text,
    health_cert: candidate.health_cert,
    source_channel: candidate.source_channel,
    station_id: candidate.station_id,
    station_name: candidate.station_name,
    status: candidate.status,
    intent_level: candidate.intent_level,
    consent_version: candidate.consent_version,
    consent_at: candidate.consent_at,
    created_at: candidate.created_at,
    updated_at: candidate.updated_at,
  };
  if (!withDetail) return base;
  return {
    ...base,
    qualification: candidate.qualification,
    conversation_summary: candidate.conversation_summary,
    conversation_key_points: candidate.conversation_key_points,
    transcript: candidate.transcript,
    audit_log: candidate.audit_log,
    interview_slots: candidate.interview_slots,
    interviews: db.interviews
      .filter((i) => i.candidate_id === candidate.id)
      .map((i) => ({ ...i })),
  };
}

function serializeStation(station) {
  return {
    ...station,
    remaining: Math.max(0, station.open_quota - station.booked),
    status: station.open_quota - station.booked > 0 ? 'active' : 'full',
  };
}

function findCandidate(id) {
  const candidate = db.candidates.find((c) => c.id === id);
  if (!candidate) throw apiError('CANDIDATE_NOT_FOUND', '候选人不存在', 404);
  return candidate;
}

function refreshStationCounts() {
  db.stations.forEach((station) => {
    station.remaining = Math.max(0, station.open_quota - station.booked);
    station.status = station.remaining > 0 ? 'active' : 'full';
  });
}

/* ------------------------- 路由实现 ------------------------- */

function listCandidates(query) {
  const q = (query.get('q') || '').trim().toLowerCase();
  const status = query.get('status') || '';
  const source = query.get('source_channel') || '';
  const stationId = query.get('station_id') || '';
  const intent = query.get('intent_level') || '';
  const page = Math.max(1, Number(query.get('page') || 1));
  const pageSize = Math.max(1, Number(query.get('page_size') || 10));

  let items = db.candidates.slice();
  if (q) {
    items = items.filter((c) => {
      const name = fullName(c);
      const phone = fullPhone(c);
      return (
        name.toLowerCase().includes(q) ||
        phone.includes(q) ||
        c.phone_masked.includes(q) ||
        c.station_name.includes(q)
      );
    });
  }
  if (status) items = items.filter((c) => c.status === status);
  if (source) items = items.filter((c) => c.source_channel === source);
  if (stationId) items = items.filter((c) => c.station_id === stationId);
  if (intent) items = items.filter((c) => String(c.intent_level) === String(intent));

  items.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
  const total = items.length;
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize).map((c) => serializeCandidate(c)),
    total,
    page,
    page_size: pageSize,
  };
}

function patchCandidate(id, body) {
  const candidate = findCandidate(id);
  if (!body || !body.reason || String(body.reason).trim().length < 2) {
    throw apiError('REASON_REQUIRED', '修改候选人信息必须填写修改原因（至少 2 个字）', 422);
  }
  const fields = body.fields || {};
  const newAudit = [];
  const entries = Object.entries(fields);
  if (entries.length === 0) throw apiError('NO_CHANGES', '没有需要保存的修改', 422);

  entries.forEach(([key, value]) => {
    let from = '-';
    let to = value;
    let targetKey = key;
    switch (key) {
      case 'name':
      case 'name_masked': {
        if (!value) return;
        targetKey = 'name_masked';
        from = candidate.name_masked || '-';
        candidate.name_token = `tok_name_${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
        db.vault.set(candidate.name_token, value);
        candidate.name_masked = maskName(value);
        to = candidate.name_masked;
        break;
      }
      case 'phone':
      case 'phone_masked': {
        if (!value) return;
        if (!/^1\d{10}$/.test(String(value).trim())) {
          throw apiError('INVALID_PHONE', '手机号格式不正确（需 11 位数字）', 422);
        }
        targetKey = 'phone_masked';
        from = candidate.phone_masked || '-';
        candidate.phone_token = `tok_phone_${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
        db.vault.set(candidate.phone_token, String(value).trim());
        candidate.phone_masked = maskPhone(String(value).trim());
        to = candidate.phone_masked;
        break;
      }
      case 'station_id': {
        from = candidate.station_name || '-';
        candidate.station_id = value || null;
        candidate.station_name = stationName(value);
        to = candidate.station_name;
        break;
      }
      case 'has_ebike': {
        from = candidate.has_ebike ? '有' : '没有';
        candidate.has_ebike = Boolean(value);
        to = value ? '有' : '没有';
        break;
      }
      case 'job_type': {
        from = JOB_TYPE_LABEL[candidate.job_type] || candidate.job_type || '-';
        candidate.job_type = value;
        to = JOB_TYPE_LABEL[value] || value;
        break;
      }
      case 'health_cert': {
        from = HEALTH_LABEL[candidate.health_cert] || '-';
        candidate.health_cert = value;
        to = HEALTH_LABEL[value] || value;
        break;
      }
      default: {
        from = candidate[key] == null ? '-' : String(candidate[key]);
        candidate[key] = value;
        to = value == null ? '-' : String(value);
      }
    }
    newAudit.push({
      id: newId('audit'),
      at: nowIso(),
      operator: `${EMPLOYEE.name}（${EMPLOYEE.employee_no}）`,
      field: FIELD_LABELS[targetKey] || FIELD_LABELS[key] || key,
      from,
      to,
      reason: String(body.reason).trim(),
    });
  });

  candidate.audit_log = [...newAudit, ...candidate.audit_log];
  candidate.updated_at = nowIso();
  return serializeCandidate(candidate, { withDetail: true });
}

function candidateAction(id, body) {
  const candidate = findCandidate(id);
  const action = body && body.action;
  const reason = body && String(body.reason || '').trim();
  if (!reason) throw apiError('REASON_REQUIRED', '该操作必须填写理由后才能提交', 422);
  if (!['confirm_interview', 'handoff', 'reject'].includes(action)) {
    throw apiError('INVALID_ACTION', '不支持的操作', 422);
  }

  const labels = {
    confirm_interview: '确认面试',
    handoff: '转人工跟进',
    reject: '标记不合适',
  };

  if (action === 'confirm_interview') {
    const slotStart = body.slot_start;
    if (!slotStart) throw apiError('SLOT_REQUIRED', '确认面试需要选择面试时段', 422);
    const station = stationById(candidate.station_id) || db.stations[0];
    const slot = dayjs(slotStart);
    db.interviews.push({
      id: newId('itv'),
      candidate_id: candidate.id,
      candidate_name: candidate.name_masked,
      candidate_phone_masked: candidate.phone_masked,
      station_id: station.id,
      station_name: station.name,
      slot_start: slot.toISOString(),
      status: 'booked',
      note: reason,
    });
    station.booked += 1;
    candidate.status = 'booked';
  } else if (action === 'handoff') {
    candidate.status = 'handoff';
  } else {
    candidate.status = 'rejected';
  }

  candidate.audit_log = [
    {
      id: newId('audit'),
      at: nowIso(),
      operator: `${EMPLOYEE.name}（${EMPLOYEE.employee_no}）`,
      field: '操作',
      from: '-',
      to: labels[action],
      reason,
    },
    ...candidate.audit_log,
  ];
  candidate.updated_at = nowIso();
  refreshStationCounts();
  return serializeCandidate(candidate, { withDetail: true });
}

function login(body) {
  const username = body && String(body.username || '').trim();
  const password = body && String(body.password || '');
  if (!username || !password) {
    throw apiError('INVALID_CREDENTIALS', '请输入工号与密码', 401);
  }
  if (password.length < 4) {
    throw apiError('INVALID_CREDENTIALS', '工号或密码错误（演示账号密码任意 4 位以上）', 401);
  }
  return {
    token: `mock.jwt.${Date.now().toString(36)}.${Math.random().toString(36).slice(2, 8)}`,
    token_type: 'Bearer',
    expires_in: 7200,
    user: { ...EMPLOYEE, username },
  };
}

function detokenize(body) {
  const token = body && body.token;
  const reason = body && String(body.reason || '').trim();
  if (!token) throw apiError('INVALID_ARGUMENT', '缺少 token', 422);
  if (!reason || reason.length < 4) {
    throw apiError('REASON_REQUIRED', '查看完整号码必须填写用途理由（至少 4 个字）', 422);
  }
  const value = db.vault.get(token);
  if (!value) throw apiError('TOKEN_NOT_FOUND', '令牌不存在或已失效', 404);
  const isPhone = /^1\d{10}$/.test(value);
  const audit = {
    id: newId('detok'),
    at: nowIso(),
    operator: `${EMPLOYEE.name}（${EMPLOYEE.employee_no}）`,
    field: isPhone ? '手机号' : '姓名',
    reason,
  };
  db.detokenizeLogs.push(audit);
  return {
    value,
    audit_id: audit.id,
    field: audit.field,
    displayed_once: true,
    note: '该值仅本次返回并展示一次，前端不缓存、不写入 localStorage。',
  };
}

function tokenize(body) {
  if (!body || !body.type || !body.value) {
    throw apiError('INVALID_ARGUMENT', '缺少 type 或 value', 422);
  }
  const value = String(body.value).trim();
  const token = `tok_${body.type}_${Date.now().toString(36)}`;
  db.vault.set(token, value);
  return {
    token,
    masked: body.type === 'phone' ? maskPhone(value) : maskName(value),
  };
}

/* ------------------------- 对外路由 ------------------------- */

export async function mockRequest(method, path, body = {}) {
  await delay(LATENCY);
  const url = new URL(path, 'http://mock.local');
  const pathname = url.pathname.replace(/\/+$/, '');
  const query = url.searchParams;
  const m = method.toUpperCase();
  const authHeader = typeof window !== 'undefined' ? window.__adminToken : '';

  if (m === 'POST' && pathname === '/api/v1/auth/login') return login(body);

  // 除登录外，mock 仍要求带 Bearer token（演示联调用）。
  if (!authHeader && pathname !== '/api/v1/auth/login') {
    throw apiError('UNAUTHORIZED', '未登录或登录已过期', 401);
  }

  if (m === 'GET' && pathname === '/api/v1/admin/candidates') return listCandidates(query);

  let match = pathname.match(/^\/api\/v1\/admin\/candidates\/([^/]+)\/actions$/);
  if (m === 'POST' && match) return candidateAction(match[1], body);

  match = pathname.match(/^\/api\/v1\/admin\/candidates\/([^/]+)$/);
  if (match) {
    const candidate = findCandidate(match[1]);
    if (m === 'GET') return serializeCandidate(candidate, { withDetail: true });
    if (m === 'PATCH') return patchCandidate(match[1], body);
  }

  if (m === 'GET' && pathname === '/api/v1/admin/interviews') {
    const from = query.get('from');
    const to = query.get('to');
    let items = db.interviews.slice();
    if (from) items = items.filter((i) => !dayjs(i.slot_start).isBefore(dayjs(from)));
    if (to) items = items.filter((i) => !dayjs(i.slot_start).isAfter(dayjs(to).endOf('day')));
    items.sort((a, b) => (a.slot_start < b.slot_start ? -1 : 1));
    return { interviews: items.map((i) => ({ ...i })), total: items.length };
  }

  if (m === 'GET' && pathname === '/api/v1/admin/stations') {
    return { stations: db.stations.map(serializeStation) };
  }

  match = pathname.match(/^\/api\/v1\/admin\/stations\/([^/]+)$/);
  if (m === 'PATCH' && match) {
    const station = db.stations.find((s) => s.id === match[1]);
    if (!station) throw apiError('STATION_NOT_FOUND', '站点不存在', 404);
    if (body && body.open_quota != null) {
      const quota = Number(body.open_quota);
      if (!Number.isFinite(quota) || quota < 0 || quota > 99) {
        throw apiError('INVALID_QUOTA', '名额需为 0-99 的整数', 422);
      }
      station.open_quota = Math.round(quota);
    }
    return serializeStation(station);
  }

  if (m === 'GET' && pathname === '/api/v1/admin/metrics') {
    return { ...db.metrics, generated_at: nowIso() };
  }

  if (m === 'POST' && pathname === '/api/v1/vault/detokenize') return detokenize(body);

  if (m === 'POST' && pathname === '/api/v1/vault/tokenize') return tokenize(body);

  if (m === 'GET' && pathname === '/api/v1/admin/audit/detokenize') {
    return { logs: db.detokenizeLogs.slice().reverse() };
  }

  throw apiError('NOT_FOUND', `mock 未实现该接口: ${m} ${pathname}`, 404);
}

export function resetMockDb() {
  db.detokenizeLogs = [];
  db.auditSeq = 0;
  bootstrap();
}
