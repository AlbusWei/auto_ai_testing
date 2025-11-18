# 维护文档

## 开发环境配置

- Python 3.9+ 建议
- 安装依赖：`pip install -r requirements.txt`
- 日志输出在 `logs/auto_ai_testing.log`

## 测试用例设计指南

- 数据加载
  - 覆盖CSV与Excel读取、列名规范化与必填校验、时间戳复制。
- 模型调用
  - 使用mock模拟成功与失败响应，验证重试次数与错误记录，校验输出列写入与耗时记录。
- 裁判评估
  - 模拟单值与列表评分响应，验证label写入与批量映射。

## 扩展开发说明

- API适配
  - 如模型或裁判API请求/返回结构差异，可在 `utils/parsers.py` 中扩展解析逻辑或在 `cli.py` 引入可配置的字段名。
- 批量策略
  - `batch_size` 与 `max_merge_rows` 可结合实际裁判工作流吞吐进行调整；解析器支持列表结果的映射，数量不一致时对组内广播首个值。
- 元数据
  - 可在 `model_tester.py` 与 `evaluator.py` 中添加更多元数据列，如请求ID、服务端提示、重试次数等。