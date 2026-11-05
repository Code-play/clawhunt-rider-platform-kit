import { useState } from 'react';
import { Alert, App, Button, Card, Form, Input, Tag, Typography } from 'antd';
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '../state/AuthContext.jsx';
import { API_MODE } from '../api/client.js';

export default function LoginPage() {
  const { login } = useAuth();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values) => {
    setLoading(true);
    try {
      await login(values);
      message.success('登录成功');
    } catch (err) {
      message.error(err.message || '登录失败，请检查工号与密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-brand">
        <div className="login-logo">骑</div>
        <h1>骑手招聘工作台</h1>
        <p>头部即时配送平台 · 招聘专员端</p>
      </div>

      <Card className="login-card" bordered={false}>
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          员工登录
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 20 }}>
          员工端接口统一使用 Bearer JWT；查看候选人完整手机号需填写理由并写入审计。
        </Typography.Paragraph>
        <Form
          layout="vertical"
          requiredMark={false}
          initialValues={{ username: 'A1024', password: '123456' }}
          onFinish={onFinish}
        >
          <Form.Item
            name="username"
            label="员工工号"
            rules={[{ required: true, message: '请输入员工工号' }]}
          >
            <Input prefix={<UserOutlined />} size="large" placeholder="例如 A1024" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 4, message: '密码至少 4 位' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} size="large" placeholder="演示密码 123456" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>
            登录工作台
          </Button>
        </Form>

        <Alert
          style={{ marginTop: 18 }}
          type="info"
          showIcon
          icon={<SafetyCertificateOutlined />}
          message="演示账号已预填"
          description="工号 A1024 / 密码 123456。mock 模式下任意 4 位以上密码均可登录；设置 VITE_API_BASE 后走真后端鉴权。"
        />
        <p className="login-foot">
          当前模式：{API_MODE === 'mock' ? '内置 mock（可脱离后端独立运行）' : '真后端 fetch'}
        </p>
        <Tag color="orange" style={{ marginTop: 8 }}>
          页面水印：姓名 · 工号 · 日期
        </Tag>
      </Card>
    </div>
  );
}
