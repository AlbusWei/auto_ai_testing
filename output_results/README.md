# output_results 目录

此目录用于保存模型运行后的输出数据文件（例如 `*_outputs.csv/.xlsx`）。

为了避免误将业务数据推送到远端，仅保留以下占位文件：
- `.gitkeep`：保持目录被追踪。
- `README.md`：说明用途与约定。

实际输出文件会被 `.gitignore` 忽略，不应提交到仓库。