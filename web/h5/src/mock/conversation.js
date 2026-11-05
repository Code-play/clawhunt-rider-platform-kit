/**
 * 7 槽位对话脚本引擎（确定性）：给定当前会话状态与用户输入，产出下一条 AI 回复。
 * 支持分支：政策问答（带出处卡片）、转人工、未成年 end_minor、资料收齐后站点推荐。
 * 正常流程：姓名 → 手机号 → 出生年月 → 跑单区域 → 工作类型 → 电动车 → 可到岗时间。
 */
import { CANDIDATE_FIELDS, POLICY_DOCS } from './data.js';
import { maskName, maskPhone, ageFromBirthYm } from '../lib/format.js';

export const TOTAL_SLOTS = CANDIDATE_FIELDS.length;

const SAMPLE_SUFFIX = /[（(]?\s*示例\s*[）)]?/g;

function clean(text) {
  return String(text || '')
    .replace(SAMPLE_SUFFIX, '')
    .trim();
}

function tokenize(type, value) {
  let hash = 0;
  const raw = `${type}:${value}`;
  for (let i = 0; i < raw.length; i += 1) {
    hash = (hash * 31 + raw.charCodeAt(i)) >>> 0;
  }
  return `tok_${type}_${hash.toString(36)}`;
}

const POLICY_RULES = [
  { re: /保险|意外|工伤|保障/, key: 'insurance' },
  { re: /结算|工资|发薪|报酬|单价|补贴/, key: 'settlement' },
  { re: /入职|到站|体检|健康证|装备|流程|培训/, key: 'onboarding' },
  { re: /隐私|信息保护|删除|授权|安全/, key: 'privacy' },
];

const STEPS = [
  {
    key: 'name',
    label: '姓名',
    quick: ['张伟（示例）', '李娜（示例）'],
    question: '先问一下，怎么称呼你？',
    hint: '请直接回复你的姓名（2-12 个字，不含数字）。',
    normalize(text) {
      const v = clean(text).replace(/\s+/g, '');
      if (v.length < 1 || v.length > 12 || /\d/.test(v)) return { ok: false };
      return { ok: true, value: v };
    },
    apply(candidate, value) {
      candidate.name_token = tokenize('name', value);
      candidate.name_masked = maskName(value);
    },
    display: () => '',
    ack: (candidate, value) => `已记录（${maskName(value)}）。`,
  },
  {
    key: 'phone',
    label: '手机号',
    quick: ['13800138000（示例）'],
    question: '请提供你的手机号，用于预约通知和招聘专员联系。',
    hint: '手机号需为 11 位数字，例如 13800138000。',
    normalize(text) {
      const digits = clean(text).replace(/\D/g, '');
      if (!/^1\d{10}$/.test(digits)) return { ok: false };
      return { ok: true, value: digits };
    },
    apply(candidate, value) {
      candidate.phone_token = tokenize('phone', value);
      candidate.phone_masked = maskPhone(value);
    },
    ack: (candidate, value) => `手机号已登记（${maskPhone(value)}），仅用于预约与跟进。`,
  },
  {
    key: 'birth_ym',
    label: '出生年月',
    quick: ['1998-05（示例）', '2010-01（未成年分支）'],
    question: '你的出生年月是？（如 1998-05）',
    hint: '请按「YYYY-MM」回复出生年月，例如 1998-05。',
    normalize(text) {
      const v = clean(text).replace(/\s+/g, '');
      let year;
      let month;
      let m = v.match(/^(\d{4})\s*[-/.年]\s*(\d{1,2})/);
      if (!m) m = v.match(/^(\d{4})(\d{2})$/);
      if (!m) return { ok: false };
      year = Number(m[1]);
      month = Number(m[2]);
      const nowYear = new Date().getFullYear();
      if (year < 1940 || year > nowYear || month < 1 || month > 12) return { ok: false };
      const ym = `${year}-${String(month).padStart(2, '0')}`;
      const age = ageFromBirthYm(ym);
      return { ok: true, value: ym, age };
    },
    apply(candidate, value) {
      candidate.birth_ym = value;
    },
    ack: (candidate, value) => `出生年月已记录（${value}）。`,
  },
  {
    key: 'area_text',
    label: '跑单区域',
    quick: ['浦东新区', '闵行区', '徐汇区'],
    question: '你主要在哪个区域跑单？（填到区/街道即可，如 浦东新区）',
    hint: '请填写你方便的跑单区域，例如「浦东新区」「张江」。',
    normalize(text) {
      const v = clean(text).replace(/[，,。.]/g, '');
      if (v.length < 2 || v.length > 30) return { ok: false };
      return { ok: true, value: v };
    },
    apply(candidate, value) {
      candidate.area_text = value;
    },
    ack: () => '',
  },
  {
    key: 'job_type',
    label: '工作类型',
    quick: ['全职', '兼职', '还没想好'],
    question: '你想做全职还是兼职？',
    hint: '请回复「全职」「兼职」或「还没想好」。',
    normalize(text) {
      const v = clean(text);
      let jobType = null;
      if (/全职|专职|fulltime/i.test(v)) jobType = 'fulltime';
      else if (/兼职|parttime/i.test(v)) jobType = 'parttime';
      else if (/还没想好|不确定|都行|undecided/i.test(v)) jobType = 'undecided';
      if (!jobType) return { ok: false };
      return { ok: true, value: jobType };
    },
    apply(candidate, value) {
      candidate.job_type = value;
    },
    ack: (candidate, value) =>
      `工作类型已记录（${{ fulltime: '全职', parttime: '兼职', undecided: '还没想好' }[value]}）。`,
  },
  {
    key: 'has_ebike',
    label: '是否有电动车',
    quick: ['有', '没有', '可以租'],
    question: '你现在有电动车吗？',
    hint: '请回复「有」「没有」或「可以租」。',
    normalize(text) {
      const v = clean(text);
      if (/^(有|有车|有电动车|yes|y)$/i.test(v) || /有.*电动车/.test(v)) {
        return { ok: true, value: true, display: '有' };
      }
      if (/没有|无车|没车|^无$|^没有$|no|^n$/i.test(v)) {
        return { ok: true, value: false, display: '没有' };
      }
      if (/可以租|租赁|租车|能租/.test(v)) {
        return { ok: true, value: false, display: '可以租' };
      }
      return { ok: false };
    },
    apply(candidate, value) {
      candidate.has_ebike = value;
    },
    ack: (candidate, value) => `已记录（${value ? '有' : '没有/可租'}电动车）。`,
  },
  {
    key: 'start_text',
    label: '可到岗时间',
    quick: ['明天', '本周内', '下个月'],
    question: '你最快什么时候能到岗？',
    hint: '请回复可到岗时间，例如「明天」「本周内」「下个月」。',
    normalize(text) {
      const v = clean(text);
      if (v.length < 1 || v.length > 30) return { ok: false };
      return { ok: true, value: v };
    },
    apply(candidate, value) {
      candidate.start_text = value;
    },
    ack: (candidate, value) => `可到岗时间已记录（${value}）。`,
  },
];

export function createSessionState(candidateId) {
  const now = Date.now();
  return {
    id: `sess_${now.toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    candidate_id: candidateId,
    step: 0,
    collected: {},
    replied: {},
    handed_off: false,
    minor: false,
    status: 'collecting',
    created_at: new Date().toISOString(),
  };
}

export function buildProgress(session) {
  const fields = STEPS.map((step) => ({
    key: step.key,
    label: step.label,
    collected: Boolean(session.collected[step.key]),
  }));
  return {
    done: fields.filter((f) => f.collected).length,
    total: TOTAL_SLOTS,
    fields,
  };
}

export function buildGreeting(session) {
  return {
    text:
      '你好，我是骑手招募助手，可以帮你了解岗位、推荐附近站点并预约面试。\n' +
      '本次登记共 7 项信息，大约 2 分钟；你随时可以要求转人工。\n' +
      STEPS[0].question,
    quick_replies: STEPS[0].quick,
    progress: buildProgress(session),
    actions: [],
  };
}

export function currentQuickReplies(session) {
  if (session.handed_off || session.minor) return [];
  if (session.step >= STEPS.length) return ['查看推荐站点', '转人工'];
  const step = STEPS[session.step];
  return step ? step.quick : [];
}

function stationPayload(stations) {
  return stations
    .filter((s) => s.open_quota > 0)
    .sort((a, b) => a.distance_km - b.distance_km)
    .slice(0, 3)
    .map((s) => ({
      id: s.id,
      name: s.name,
      address: s.address,
      distance_km: s.distance_km,
      open_quota: s.open_quota,
      slots: s.slots.filter((slot) => slot.available).slice(0, 3),
    }));
}

function matchPolicy(text) {
  for (const rule of POLICY_RULES) {
    if (rule.re.test(text)) {
      const doc = POLICY_DOCS[rule.key];
      return {
        reply: doc.answer,
        policy_card: {
          doc_id: doc.id,
          title: doc.title,
          version: doc.version,
          effective_date: doc.effective_date,
          answer: doc.answer,
          disclaimer: doc.disclaimer,
        },
        source_label: `出处：${doc.title} ${doc.version}（生效日期 ${doc.effective_date}）`,
      };
    }
  }
  return null;
}

/**
 * 处理一条求职者消息。
 * @returns {{reply, quick_replies, progress, actions, policy_card?, stations?, source_label?}}
 */
export function handleMessage({ session, candidate, text, stations, includeGreeting = false }) {
  const raw = String(text || '').trim();
  const progress = buildProgress(session);

  if (session.minor) {
    return {
      reply: '本次登记已结束：平台要求骑手年满 18 周岁，感谢你的关注。如需了解其他岗位，可转人工咨询。',
      quick_replies: [],
      progress,
      actions: [],
    };
  }

  if (session.handed_off) {
    return {
      reply: '已为你转接人工招聘专员，预计 10 分钟内电话联系你。你也可以直接拨打招聘热线 400-820-1234。',
      quick_replies: [],
      progress,
      actions: ['handoff'],
    };
  }

  if (!raw) {
    return {
      reply: `我在听～ ${currentQuestion(session)}`,
      quick_replies: currentQuickReplies(session),
      progress,
      actions: [],
    };
  }

  // 分支 1：政策问答（不推进槽位）
  if (raw !== '你好' && !includeGreeting) {
    const policy = matchPolicy(raw);
    if (policy) {
      return {
        reply: `关于这个问题，我查到《${policy.policy_card.title.replace(/[《》]/g, '')}》${
          policy.policy_card.version
        } 的说明，摘要见下方政策卡（含出处与免责声明）。`,
        quick_replies: currentQuickReplies(session),
        progress,
        actions: [],
        policy_card: policy.policy_card,
        source_label: policy.source_label,
      };
    }
  }

  // 分支 2：转人工
  if (/转人工|人工客服|找人工|真人|热线/.test(raw)) {
    session.handed_off = true;
    session.status = 'handoff';
    candidate.status = 'handoff';
    candidate.updated_at = new Date().toISOString();
    return {
      reply:
        '好的，已为你转接人工招聘专员，预计 10 分钟内电话联系你；如需立即沟通可拨打招聘热线 400-820-1234。你的已填信息会一并交给专员。',
      quick_replies: [],
      progress,
      actions: ['handoff'],
    };
  }

  // 分支 3：未成年（显式表述或出生年月不满足 18 周岁）
  if (/未成年|没满\s*18|未满\s*18|不满\s*18|16\s*岁|17\s*岁/.test(raw)) {
    return endMinor(session, candidate);
  }

  // 正常流程：收集当前槽位
  if (session.step < STEPS.length) {
    const step = STEPS[session.step];
    const parsed = step.normalize(raw);
    if (!parsed.ok) {
      return {
        reply: `这个信息我没能识别～ ${step.hint}\n${step.question}`,
        quick_replies: step.quick,
        progress,
        actions: [],
      };
    }

    if (step.key === 'birth_ym' && parsed.age != null && parsed.age < 18) {
      step.apply(candidate, parsed.value);
      session.collected[step.key] = parsed.value;
      candidate.updated_at = new Date().toISOString();
      return endMinor(session, candidate);
    }

    step.apply(candidate, parsed.value);
    session.collected[step.key] = parsed.display || parsed.value;
    session.step += 1;
    candidate.updated_at = new Date().toISOString();

    const ack = step.ack ? step.ack(candidate, parsed.value) : '';
    const nextProgress = buildProgress(session);

    if (session.step >= STEPS.length) {
      session.status = 'complete';
      candidate.status = 'complete';
      const recommended = stationPayload(stations);
      return {
        reply:
          `${ack}7 项信息已收集完成。\n` +
          '我按你的跑单区域和可到岗时间，筛选了 3 个在招站点（含距离、在招人数与可约时段），选一个时段就能直接预约面试。',
        quick_replies: ['想先看政策', '转人工'],
        progress: nextProgress,
        actions: ['show_stations'],
        stations: recommended,
      };
    }

    const nextStep = STEPS[session.step];
    return {
      reply: `${ack}${nextStep.question}`,
      quick_replies: nextStep.quick,
      progress: nextProgress,
      actions: [],
    };
  }

  // 已收齐后的自由问答：政策 / 转人工已在上面处理，其余给出站点卡片
  return {
    reply: '你的资料已收齐。如果还想调整时间，可以在预约结果页改约或取消；也可以直接选一个站点预约。',
    quick_replies: ['查看推荐站点', '转人工'],
    progress,
    actions: ['show_stations'],
    stations: stationPayload(stations),
  };
}

function endMinor(session, candidate) {
  session.minor = true;
  session.status = 'minor';
  candidate.status = 'rejected';
  candidate.updated_at = new Date().toISOString();
  return {
    reply:
      '抱歉，平台骑手岗位要求年满 18 周岁，你目前未满 18 岁，暂时无法登记和预约。\n' +
      '本次登记到此结束，已填写的信息不会继续使用；如有疑问可转人工或拨打招聘热线 400-820-1234。',
    quick_replies: [],
    progress: buildProgress(session),
    actions: ['end_minor'],
  };
}

function currentQuestion(session) {
  if (session.step >= STEPS.length) return '你可以选择站点预约，或继续问我岗位/政策问题。';
  return STEPS[session.step].question;
}

export { STEPS as SLOT_STEPS };
