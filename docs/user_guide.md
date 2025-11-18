# 使用手册

## 测试准备

- 测试集格式(Excel/CSV)需包含以下列：
  - `序号`(唯一标识)
  - `scenario`(场景分类，可选，仅用于管理)
  - `input`(模型输入文本)
  - `ground_truth`(参考答案或要求描述)
  - `city`(城市名称，可选，仅用于POI场景)
- 可使用 `test_sets/example.csv` 作为示例。

## 执行流程说明

1. 数据加载与复制
   - 工具从指定路径读取测试集，复制到 `test_sets` 目录，并在文件名后追加执行时间戳 `YYYYMMDD_HHMMSS`。
2. 模型测试
   - 逐行调用模型API，支持重试(默认3次)与超时控制，记录每个请求的耗时与状态码，在数据中新增 `output` 列存放模型响应。
   - 输出文件保存至 `output_results` 目录。
3. 裁判评估
   - 集成Dify工作流API作为裁判模型，将 `ground_truth` 与 `output` 拼接或打包为裁判输入，返回0/1或连续分值，新增 `label` 列。
   - 评估文件保存至 `evaluation_results` 目录。

## 结果解读指南

- `output`: 模型返回的文本或解析后的主要字段。
- `request_elapsed_ms`: 模型请求耗时，越小越好。
- `response_status`: 模型HTTP状态码，2xx表示成功。
- `label`: 裁判评分，默认0/1，亦兼容连续分值以支持未来扩展。
- `judge_elapsed_ms`: 裁判评估请求耗时。
- `error` / `judge_error`: 发生异常或非2xx响应时记录的错误信息。

## 常见问题排查

- 无法读取测试集
  - 确认文件路径与扩展名是否正确(`.csv`/`.xlsx`)。
  - Excel需安装 `openpyxl`。执行 `pip install -r requirements.txt`。
- 模型调用失败
  - 检查 `model_api.endpoint` 与 `model_api.api_key` 是否配置。
  - 观察 `logs/auto_ai_testing.log` 中的错误详情与状态码。
  - 适当增大 `timeout` 或 `retries`。
- 裁判评分解析失败
  - 确认裁判API返回包含 `score` 或可解析的文本数字。
  - 如果裁判返回列表，确保与批量大小一致；否则将使用首个值广播。
- 输出/评估文件未生成
  - 检查 `paths.output_results_dir` 与 `paths.evaluation_results_dir` 权限。
  - 查看日志中是否有保存路径或写入错误。