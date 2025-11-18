# 自动化测试AI模型工具

一个用于批量执行模型测试、记录输出并集成裁判工作流评估的Python工具。支持CSV/Excel测试集，提供配置文件管理与命令行入口，输出详尽日志与元数据。

## 架构图

```
test_sets/ (原始测试集)
        └─ example.csv

data_loader.py  —— 加载并复制测试集(带时间戳)
model_tester.py —— 调用模型API，写入output与请求元数据
evaluator.py    —— 调用裁判(Dify工作流)评估，写入label与评估元数据
utils/          —— 文件、HTTP重试、解析器、日志、配置工具
cli.py          —— 命令行入口(test/evaluate/run)

output_results/     —— 模型输出文件
evaluation_results/ —— 裁判评估结果文件
logs/               —— 执行日志
```

## 快速开始

- 安装依赖

```
pip install -r requirements.txt
```

- 准备配置文件

复制 `config.ini.example` 为 `config.ini`，填写模型与裁判API（默认已按Dify格式设置）：

```
[model_api]
endpoint = https://api.dify.ai/v1/completion-messages
api_key = YOUR_MODEL_API_KEY
input_field = text
timeout = 30
retries = 3
kind = dify_completion

[judge_api]
endpoint = https://api.dify.ai/v1/workflows/execute
api_key = YOUR_JUDGE_API_KEY
batch_size = 1
max_merge_rows = 1
timeout = 30
retries = 3
kind = dify_workflow

[paths]
test_sets_dir = test_sets
output_results_dir = output_results
evaluation_results_dir = evaluation_results

[execution]
dataset = test_sets/example.csv
user = auto-ai-testing
```

- 执行

```
# 仅运行模型测试
python cli.py test --config config.ini

# 仅对已有输出文件评估
python cli.py evaluate --config config.ini --input output_results/<文件名>.csv

# 先测试模型再评估
python cli.py run --config config.ini
```

## 配置文件说明

- `model_api`: 模型端点、密钥、输入字段、超时与重试。
- `judge_api`: 裁判(Dify工作流)端点、密钥、批量大小、合并行数、超时与重试。
- `paths`: 测试集、输出与评估结果目录。
- `execution`: 可选的默认数据集路径。

## 命令行参数说明

- 通用：`--config`、`--dataset`、`--model-endpoint`、`--model-api-key`、`--input-field`、`--model-timeout`、`--model-retries`、`--model-kind`、`--judge-endpoint`、`--judge-api-key`、`--batch-size`、`--max-merge-rows`、`--judge-timeout`、`--judge-retries`、`--judge-kind`、`--user-id`
- `test`: 只执行模型测试。
- `evaluate`: 只执行评估，需要 `--input` 指定模型输出文件。
- `run`: 先测试再评估。

## 质量保证

- 输入数据验证：校验 `序号(id)` 唯一、`input` 非空。
- 异常处理机制：HTTP异常与非2xx响应均记录错误信息。
- 详细日志：控制台与文件日志，含时间戳与上下文。
- 元数据输出：请求耗时(`request_elapsed_ms`)、状态码(`response_status`)、评估耗时(`judge_elapsed_ms`)等。

## Dify对接说明

- 模型测试（completion-messages）：payload 形如 `{"inputs": {"text": "..."}, "response_mode": "blocking", "user": "..."}`。
- 模型测试（chat-messages）：可通过 `--model-kind dify_chat` 使用 `{"inputs": {}, "query": "...", "response_mode": "blocking", "user": "..."}`。
- 裁判评估（workflows/execute）：payload 形如 `{"inputs": {"ground_truth": "...", "output": "..."}, "response_mode": "blocking", "user": "..."}`；批量模式会将多行封装为 `inputs.items=[{ground_truth, output}, ...]`。
- 响应解析：支持从 `answer`、`outputs.output_text` 等字段抽取文本；评分解析支持 `outputs.score` 或文本中的数字。

## 文档

- 使用手册：见 `docs/user_guide.md`
- 维护文档：见 `docs/maintenance.md`