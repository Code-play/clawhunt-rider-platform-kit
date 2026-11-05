/**
 * H5 端内置 mock 的静态数据：告知同意书、政策文档、站点与可约时段。
 * 所有日期基于运行当天生成，保证仓库隔天打开仍然「有档期」。
 */

export const CONSENT_VERSION = 'v1.2';
export const AI_NOTICE = '本服务由 AI 提供 · 可随时转人工';
export const HOTLINE = '400-820-1234';

export const CONSENT_DOC = {
  version: CONSENT_VERSION,
  effective_date: '2026-09-01',
  title: '个人信息收集告知书',
  collect: [
    '姓名（仅用于对接与到站核验）',
    '手机号（仅用于预约通知与招聘专员联系）',
    '出生年月（用于年龄与岗位合规校验）',
    '跑单区域、工作类型（全职/兼职）、是否有电动车、可到岗时间（用于岗位与站点匹配）',
  ],
  not_collect: [
    '身份证号、银行卡号、社保号等证件号码',
    '人脸、指纹等生物识别信息',
    '精确位置轨迹（仅按你填写的区域文字做站点推荐）',
    '健康诊断、病历等医疗信息（仅在到站时由你自行出示健康证，不采集证号）',
  ],
  purposes: [
    '生成骑手求职档案，为你匹配岗位与站点',
    '推荐附近站点、可约时段并完成面试预约',
    '由招聘专员跟进答疑与到站引导',
  ],
  retention:
    '未入职的求职信息自最后一次互动起 30 天后自动删除；入职后转为企业人事档案并按劳动用工相关法规保存。',
  rights: [
    '查看与更正：随时查看已收集字段并自行修正',
    '获取副本：一键下载你的信息副本（JSON）',
    '撤回授权并删除：撤回后立即删除本次登记信息与本地会话',
    '人工协助：随时要求转人工，或拨打招聘热线',
  ],
  ai_note:
    '本页面与后续对话由 AI 提供服务，AI 生成内容仅供参考，不构成录用承诺；你可随时要求转人工。',
};

export const POLICY_DOCS = {
  insurance: {
    id: 'POL-INS-2026',
    title: '《骑手合作保障与商业保险说明》',
    version: 'v2026.3',
    effective_date: '2026-03-01',
    updated_at: '2026-09-15',
    answer:
      '平台为完成实名认证且当日接单的骑手投保当日意外险，保障含意外身故/伤残与意外医疗；保险由合作保险公司承保，接单当日生效、次日零时失效，无需骑手付费。',
    disclaimer:
      '以上为政策摘要，具体保障范围、免赔额与理赔流程以承保保险公司条款和你签署的《合作服务协议》为准。',
  },
  settlement: {
    id: 'POL-SET-2026',
    title: '《骑手报酬与结算规则》',
    version: 'v2026.2',
    effective_date: '2026-05-01',
    updated_at: '2026-08-20',
    answer:
      '全职骑手按月结算（每月 10 日发放上月报酬），兼职骑手支持按周结算；单价按站点距离分段计价，恶劣天气与高峰时段有补贴，具体单价以站点公示为准。',
    disclaimer:
      '以上为规则摘要，最终以你所在站点的《报酬结算确认单》与平台公示规则为准。',
  },
  onboarding: {
    id: 'POL-ONB-2026',
    title: '《骑手到站与入职流程说明》',
    version: 'v2026.1',
    effective_date: '2026-02-01',
    updated_at: '2026-07-01',
    answer:
      '到站需携带本人身份证、健康证（食品配送岗位）与可正常使用的智能手机；流程为签到 → 资料核验 → 安全培训（约 40 分钟）→ 装备领取 → 跟车试跑。',
    disclaimer:
      '不同站点流程略有差异，请以预约成功后站长电话通知为准。',
  },
  privacy: {
    id: 'POL-PRV-2026',
    title: '《个人信息保护政策》',
    version: 'v1.2',
    effective_date: '2026-09-01',
    updated_at: '2026-09-01',
    answer:
      '我们仅收集招聘匹配所必需的信息，姓名与手机号在系统内以令牌化方式存储，招聘专员查看完整手机号需填写用途理由并留痕；你可以随时查看、更正、下载副本或撤回授权并删除。',
    disclaimer:
      '本卡片为摘要，完整条款以《个人信息收集告知书 v1.2》为准。',
  },
};

const SLOT_TIMES = ['09:00', '13:30', '16:00'];

function pad(n) {
  return String(n).padStart(2, '0');
}

function formatSlot(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 生成未来 3 天的可约时段；capacity/booked 用确定性规则，刷新结果稳定。 */
export function buildSlots(seed = 1) {
  const slots = [];
  const now = new Date();
  for (let d = 1; d <= 3; d += 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + d);
    SLOT_TIMES.forEach((time, index) => {
      const [hh, mm] = time.split(':').map(Number);
      const dt = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hh, mm);
      const capacity = 3;
      const pattern = (seed * 7 + d * 3 + index) % 5;
      const booked = pattern === 0 ? 3 : pattern % 3;
      slots.push({
        slot_start: formatSlot(dt),
        capacity,
        booked,
        available: booked < capacity,
      });
    });
  }
  return slots;
}

const STATION_DEFS = [
  {
    id: 'st_zhangjiang',
    name: '张江高科站',
    address: '浦东新区张江路 88 号（地铁 2 号线张江高科站 1 号口步行 300 米）',
    area: '浦东新区',
    lat: 31.2015,
    lng: 121.589,
    distance_km: 1.2,
    open_quota: 12,
    manager_virtual_no: '4000001234',
    manager_display_no: '400-000-1234',
    seed: 1,
  },
  {
    id: 'st_shijigongyuan',
    name: '世纪公园站',
    address: '浦东新区锦绣路 1001 号（世纪公园 7 号门对面）',
    area: '浦东新区',
    lat: 31.219,
    lng: 121.556,
    distance_km: 2.8,
    open_quota: 8,
    manager_virtual_no: '4000001235',
    manager_display_no: '400-000-1235',
    seed: 2,
  },
  {
    id: 'st_jinqiao',
    name: '金桥站',
    address: '浦东新区金桥路 1388 号（金桥国际商业广场旁）',
    area: '浦东新区',
    lat: 31.257,
    lng: 121.59,
    distance_km: 4.1,
    open_quota: 5,
    manager_virtual_no: '4000001236',
    manager_display_no: '400-000-1236',
    seed: 3,
  },
  {
    id: 'st_lujiazui',
    name: '陆家嘴站',
    address: '浦东新区浦东南路 500 号（陆家嘴中心绿地东侧）',
    area: '浦东新区',
    lat: 31.2397,
    lng: 121.4998,
    distance_km: 5.6,
    open_quota: 3,
    manager_virtual_no: '4000001237',
    manager_display_no: '400-000-1237',
    seed: 4,
  },
  {
    id: 'st_chuansha',
    name: '川沙站',
    address: '浦东新区川沙新镇川环南路 200 号',
    area: '浦东新区',
    lat: 31.185,
    lng: 121.7,
    distance_km: 9.8,
    open_quota: 0,
    manager_virtual_no: '4000001238',
    manager_display_no: '400-000-1238',
    seed: 5,
  },
];

export function buildStations() {
  return STATION_DEFS.map((def) => ({
    ...def,
    slots: buildSlots(def.seed),
  }));
}

export const CANDIDATE_FIELDS = [
  { key: 'name', label: '姓名' },
  { key: 'phone', label: '手机号' },
  { key: 'birth_ym', label: '出生年月' },
  { key: 'area_text', label: '跑单区域' },
  { key: 'job_type', label: '工作类型' },
  { key: 'has_ebike', label: '是否有电动车' },
  { key: 'start_text', label: '可到岗时间' },
];

export const ARRIVAL_NOTICE = [
  '请携带本人身份证原件，到站后在签到机或站长处登记。',
  '食品配送岗位请带健康证；没有健康证可到站咨询办理指引。',
  '建议提前 10 分钟到站，迟到超过 20 分钟需重新预约。',
  '到站前如无法按时到达，请在「我的信息 - 预约」里改约或取消。',
];
