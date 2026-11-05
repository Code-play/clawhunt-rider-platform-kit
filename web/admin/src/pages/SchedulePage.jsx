import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  App,
  Button,
  Card,
  DatePicker,
  Empty,
  Segmented,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import * as api from '../api/client.js';
import { formatSlot } from '../lib/utils.js';

const HOURS = Array.from({ length: 10 }, (_, i) => 9 + i);

const INTERVIEW_STATUS = {
  booked: { text: '待面试', color: 'gold' },
  done: { text: '已到访', color: 'green' },
  no_show: { text: '未到访', color: 'red' },
  cancelled: { text: '已取消', color: 'default' },
};

function mondayOf(date) {
  const diff = (date.day() + 6) % 7;
  return date.subtract(diff, 'day').startOf('day');
}

export default function SchedulePage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [mode, setMode] = useState('week');
  const [weekStart, setWeekStart] = useState(() => mondayOf(dayjs()));
  const [dayDate, setDayDate] = useState(() => dayjs().startOf('day'));
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stations, setStations] = useState([]);
  const [stationFilter, setStationFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = mode === 'week' ? weekStart : dayDate;
      const to = mode === 'week' ? weekStart.add(6, 'day') : dayDate;
      const res = await api.listInterviews({
        from: from.startOf('day').toISOString(),
        to: to.endOf('day').toISOString(),
      });
      setInterviews(res.interviews || []);
    } catch (err) {
      message.error(err.message || '日程加载失败');
    } finally {
      setLoading(false);
    }
  }, [mode, weekStart, dayDate, message]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .listStations()
      .then((res) => setStations(res.stations || []))
      .catch(() => setStations([]));
  }, []);

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => weekStart.add(i, 'day')),
    [weekStart],
  );

  const filtered = useMemo(
    () => interviews.filter((itv) => (stationFilter ? itv.station_id === stationFilter : true)),
    [interviews, stationFilter],
  );

  const cellMap = useMemo(() => {
    const map = {};
    filtered.forEach((itv) => {
      const date = dayjs(itv.slot_start);
      const dayIndex = date.diff(weekStart, 'day');
      const key = `${dayIndex}-${date.hour()}`;
      if (!map[key]) map[key] = [];
      map[key].push(itv);
    });
    return map;
  }, [filtered, weekStart]);

  const dayInterviews = useMemo(
    () =>
      filtered
        .filter((itv) => dayjs(itv.slot_start).isSame(dayDate, 'day'))
        .sort((a, b) => (a.slot_start < b.slot_start ? -1 : 1)),
    [filtered, dayDate],
  );

  const shift = (delta) => {
    if (mode === 'week') setWeekStart((prev) => prev.add(delta * 7, 'day'));
    else setDayDate((prev) => prev.add(delta, 'day'));
  };

  const goToday = () => {
    if (mode === 'week') setWeekStart(mondayOf(dayjs()));
    else setDayDate(dayjs().startOf('day'));
  };

  const stationOptions = stations.map((s) => ({ value: s.id, label: s.name }));

  const toolbar = (
    <Space wrap>
      <Segmented
        options={[
          { label: '日视图', value: 'day' },
          { label: '周视图', value: 'week' },
        ]}
        value={mode}
        onChange={setMode}
      />
      <Button icon={<LeftOutlined />} onClick={() => shift(-1)} />
      <Button onClick={goToday}>今天</Button>
      <Button icon={<RightOutlined />} onClick={() => shift(1)} />
      <DatePicker
        allowClear={false}
        value={mode === 'week' ? weekStart : dayDate}
        onChange={(value) => {
          if (!value) return;
          if (mode === 'week') setWeekStart(mondayOf(value));
          else setDayDate(value.startOf('day'));
        }}
      />
      <Select
        allowClear
        placeholder="筛选站点"
        style={{ width: 170 }}
        options={stationOptions}
        value={stationFilter || undefined}
        onChange={(value) => setStationFilter(value || '')}
      />
      <Tag color="blue">
        {mode === 'week'
          ? `${weekStart.format('MM-DD')} ~ ${weekStart.add(6, 'day').format('MM-DD')}`
          : dayDate.format('YYYY-MM-DD')}
        ：{filtered.length} 场面试
      </Tag>
    </Space>
  );

  return (
    <div className="page-stack">
      <Card size="small">
        <div className="list-head">
          <div>
            <Typography.Title level={5} style={{ margin: 0 }}>
              面试日程
            </Typography.Title>
            <Typography.Text type="secondary">
              日 / 周视图 · 点击面试块进入候选人详情 · 数据来自 mock / 真后端
            </Typography.Text>
          </div>
          <Space wrap size={4}>
            {Object.entries(INTERVIEW_STATUS).map(([key, meta]) => (
              <Tag key={key} color={meta.color}>
                {meta.text}
              </Tag>
            ))}
          </Space>
        </div>
        <div style={{ marginTop: 14 }}>{toolbar}</div>
      </Card>

      {loading ? (
        <Card size="small">
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      ) : mode === 'week' ? (
        <Card size="small" styles={{ body: { padding: 0 } }}>
          <div className="week-grid">
            <div className="week-head">
              <div className="week-gutter" />
              {weekDays.map((day) => (
                <div
                  key={day.format('YYYY-MM-DD')}
                  className={
                    day.isSame(dayjs(), 'day') ? 'week-day week-day-today' : 'week-day'
                  }
                >
                  <b>{day.format('MM-DD')}</b>
                  <span>{day.format('ddd')}</span>
                </div>
              ))}
            </div>
            {HOURS.map((hour) => (
              <div className="week-row" key={hour}>
                <div className="week-gutter">{String(hour).padStart(2, '0')}:00</div>
                {weekDays.map((day, dayIndex) => {
                  const items = cellMap[`${dayIndex}-${hour}`] || [];
                  return (
                    <div
                      key={`${day.format('MM-DD')}-${hour}`}
                      className={day.isSame(dayjs(), 'day') ? 'week-cell today' : 'week-cell'}
                    >
                      {items.map((itv) => {
                        const meta = INTERVIEW_STATUS[itv.status] || INTERVIEW_STATUS.booked;
                        return (
                          <button
                            key={itv.id}
                            type="button"
                            className={`itv-block itv-${itv.status}`}
                            onClick={() => navigate(`/candidates/${itv.candidate_id}`)}
                            title={`${itv.candidate_name} · ${itv.station_name} · ${meta.text}`}
                          >
                            <b>{itv.candidate_name}</b>
                            <span>
                              {dayjs(itv.slot_start).format('HH:mm')} · {itv.station_name}
                            </span>
                            <Tag color={meta.color} className="itv-tag">
                              {meta.text}
                            </Tag>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card size="small" title={dayDate.format('YYYY-MM-DD dddd')}>
          {dayInterviews.length === 0 ? (
            <Empty description="当天暂无面试安排" />
          ) : (
            <div className="day-list">
              {dayInterviews.map((itv) => {
                const meta = INTERVIEW_STATUS[itv.status] || INTERVIEW_STATUS.booked;
                return (
                  <button
                    key={itv.id}
                    type="button"
                    className="day-itv"
                    onClick={() => navigate(`/candidates/${itv.candidate_id}`)}
                  >
                    <div className="day-itv-time">
                      <b>{dayjs(itv.slot_start).format('HH:mm')}</b>
                      <span>{dayjs(itv.slot_start).format('ddd')}</span>
                    </div>
                    <div className="day-itv-main">
                      <div>
                        <b>{itv.candidate_name}</b>
                        <span className="muted mono" style={{ marginLeft: 8 }}>
                          {itv.candidate_phone_masked}
                        </span>
                        <Tag color={meta.color} style={{ marginLeft: 8 }}>
                          {meta.text}
                        </Tag>
                      </div>
                      <div className="muted">
                        {itv.station_name} · {itv.note || '待面试'} · 面试时段 {formatSlot(itv.slot_start)}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
