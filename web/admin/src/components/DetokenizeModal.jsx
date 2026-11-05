import { useState } from 'react';
import { Alert, App, Button, Form, Input, Modal, Space, Typography } from 'antd';
import { CopyOutlined, LockOutlined } from '@ant-design/icons';
import * as api from '../api/client.js';

/**
 * 查看完整手机号：必须填写理由 → 调 vault/detokenize → 只展示一次。
 * 关闭弹窗即清空组件内 state；不写入 localStorage / sessionStorage / URL。
 */
export default function DetokenizeModal({ open, token, fieldLabel = '手机号', onClose }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [revealed, setRevealed] = useState(null);

  const close = () => {
    setRevealed(null);
    form.resetFields();
    onClose();
  };

  const submit = async () => {
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setLoading(true);
    try {
      const res = await api.detokenize(token, values.reason);
      setRevealed(res);
      message.success('已按理由展示一次，审计已记录');
    } catch (err) {
      message.error(err.message || '查看失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed.value);
      message.info('已复制到剪贴板，请及时清理');
    } catch {
      message.warning('当前浏览器不允许自动复制，请手动记录');
    }
  };

  const footer = revealed
    ? [
        <Button key="copy" icon={<CopyOutlined />} onClick={copy}>
          复制
        </Button>,
        <Button key="close" type="primary" onClick={close}>
          我已记录，关闭
        </Button>,
      ]
    : [
        <Button key="cancel" onClick={close}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={submit}>
          提交理由并查看
        </Button>,
      ];

  return (
    <Modal
      open={open}
      title={
        <Space>
          <LockOutlined />
          查看完整{fieldLabel}
        </Space>
      }
      onCancel={close}
      footer={footer}
      destroyOnClose
      maskClosable={false}
      width={520}
    >
      {!revealed ? (
        <>
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="查看完整号码会写入审计日志"
            description="请填写真实用途理由。号码仅本次显示一次，关闭后前端不再保留，不写入本地缓存。"
          />
          <Form form={form} layout="vertical" requiredMark>
            <Form.Item
              name="reason"
              label="查看理由"
              rules={[
                { required: true, message: '请填写查看理由' },
                { min: 4, message: '理由至少 4 个字，便于审计追溯' },
              ]}
            >
              <Input.TextArea
                rows={3}
                maxLength={200}
                showCount
                placeholder="例如：候选人电话关机，需要核对联系号码后回拨"
              />
            </Form.Item>
          </Form>
        </>
      ) : (
        <>
          <Alert
            type="success"
            showIcon
            message={`完整${fieldLabel}（仅本次显示）`}
            description={revealed.note || '关闭后前端不再保留该值。'}
          />
          <div className="detokenize-value">{revealed.value}</div>
          <Typography.Text type="secondary">审计编号：{revealed.audit_id}</Typography.Text>
        </>
      )}
    </Modal>
  );
}
