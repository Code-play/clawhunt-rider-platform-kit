import { useCallback, useEffect, useState } from 'react';
import { Alert, App, Button, Card, Col, Progress, Row, Skeleton, Space, Statistic, Tag, Tooltip, Typography } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined, ReloadOutlined } from '@ant-design/icons';
import * as api from '../api/client.js';

export default function DashboardPage() {
  const { message } = App.useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getMetrics();
      setData(res);
    } catch (err) {
      message.error(err.message || '指标加载失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="page-stack">
        <Skeleton active paragraph={{ rows: 2 }} />
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (!data) {
    return (
      <Alert
        type="error"
        showIcon
        message="指标加载失败"
        action={<Button onClick={load}>重试</Button>}
      />
    );
  }

  const funnelMax = data.funnel[0] ? data.funnel[0].value : 1;
  const channelMax = Math.max(...data.channels.map((c) => c.value));

  return (
    <div className="page-stack">
      <Alert
        type="info"
        showIcon
        message="驾驶舱示意页（任务 4/5）"
        description="7 个 KPI、转化漏斗与渠道分布均来自内置 mock 静态数据，用于示意驾驶舱形态；设置 VITE_API_BASE 后由真后端返回。"
        action={
          <Button icon={<ReloadOutlined />} onClick={load} size="small">
            刷新
          </Button>
        }
      />

      <Row gutter={[16, 16]}>
        {data.kpis.map((kpi) => {
          const up = kpi.delta >= 0;
          const maxTrend = Math.max(...kpi.trend, 1);
          return (
            <Col xs={24} sm={12} xl={8} xxl={6} key={kpi.key}>
              <Card className="kpi-card" styles={{ body: { padding: 18 } }}>
                <div className="kpi-head">
                  <span className="kpi-label">{kpi.label}</span>
                  <Tag color={up ? 'green' : 'red'} bordered={false}>
                    {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {Math.abs(kpi.delta)}%
                  </Tag>
                </div>
                <Statistic
                  value={kpi.value}
                  suffix={<span className="kpi-unit">{kpi.unit}</span>}
                  valueStyle={{ fontSize: 28, fontWeight: 600 }}
                />
                <div className="trend" aria-hidden="true">
                  {kpi.trend.map((v, i) => (
                    <i
                      key={`${kpi.key}-${i}`}
                      style={{ height: `${Math.max(12, Math.round((v / maxTrend) * 100))}%` }}
                    />
                  ))}
                </div>
              </Card>
            </Col>
          );
        })}
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="线索转化漏斗" size="small">
            {data.funnel.map((item, index) => {
              const prev = index === 0 ? item.value : data.funnel[index - 1].value;
              const rate = prev ? Math.round((item.value / prev) * 100) : 0;
              return (
                <div className="funnel-row" key={item.label}>
                  <div className="funnel-label">
                    <span>{item.label}</span>
                    <Typography.Text strong>{item.value.toLocaleString()}</Typography.Text>
                  </div>
                  <Progress
                    percent={Math.round((item.value / funnelMax) * 100)}
                    showInfo={false}
                    strokeColor={{ from: '#1677ff', to: '#69b1ff' }}
                  />
                  <span className="funnel-rate">
                    {index === 0 ? '漏斗入口' : `环节转化 ${rate}%`}
                  </span>
                </div>
              );
            })}
            <p className="card-note">数据口径示意：线索 → 有效建档 → 预约 → 到访 → 入职。</p>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="渠道来源分布" size="small">
            {data.channels.map((ch) => (
              <div className="channel-row" key={ch.name}>
                <div className="channel-head">
                  <span>{ch.name}</span>
                  <span className="muted">{ch.value} 条</span>
                </div>
                <Progress
                  percent={Math.round((ch.value / channelMax) * 100)}
                  showInfo={false}
                  strokeColor="#52c41a"
                />
              </div>
            ))}
            <p className="card-note">来源渠道与 H5 入口的 ?source_channel=xxx 参数一一对应。</p>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="指标说明">
        <Space wrap size={[24, 8]}>
          <span>
            <b>7 个 KPI</b>：新增线索、有效建档、建档完成率、预约面试、到访率、入职转化、AI 平均首响
          </span>
          <Tooltip title="骨架阶段为静态示意，后续接入真后端与埋点">
            <Tag color="default">静态示意数据</Tag>
          </Tooltip>
        </Space>
      </Card>
    </div>
  );
}
