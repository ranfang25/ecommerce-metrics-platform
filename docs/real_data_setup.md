# 官方真实数据接入

1. 打开 https://console.cloud.google.com/bigquery，创建/选择Google Cloud项目并启用BigQuery。先使用Sandbox，不要求为本项目升级付费。
2. 安装Windows Google Cloud CLI：https://docs.cloud.google.com/sdk/docs/install-sdk#windows。
3. 新开PowerShell，执行以下命令，在浏览器自行完成Google授权：

```powershell
gcloud config set project 你的项目ID
gcloud auth application-default login
```

完成后提供项目ID即可，无需把密码、令牌或认证文件发送到聊天。

4. 在项目目录运行7天链路。先仅预估扫描量，再下载；本项目默认总预估不超过10GB，超过则停止，检查后再调整参数。

```powershell
.\.venv\Scripts\python.exe -m src.extract --project 你的项目ID
.\.venv\Scripts\python.exe -m src.extract --project 你的项目ID --execute
Copy-Item config/settings.example.yml config/settings.local.yml
```

将settings.local.yml的expected_end改成2020-11-07，执行：

```powershell
.\.venv\Scripts\python.exe -m src.pipeline --config config/settings.local.yml
```

5. 小样本通过后下载完整区间（2020-11-01至2021-01-31），并将配置expected_end恢复2021-01-31：

```powershell
.\.venv\Scripts\python.exe -m src.extract --project 你的项目ID --end 2021-01-31
.\.venv\Scripts\python.exe -m src.extract --project 你的项目ID --end 2021-01-31 --execute
.\.venv\Scripts\python.exe -m src.pipeline --config config/settings.local.yml
.\.venv\Scripts\python.exe -m src.validation --config config/settings.local.yml
.\.venv\Scripts\python.exe -m src.reporting --output data/official_build
.\.venv\Scripts\python.exe -m streamlit run app.py
```

源表只读，导出SQL在sql/bigquery_extract/。每个日期分开保存Parquet并记录BigQuery job_id、字节数、行数。重新下载按日期覆盖本地派生快照；原始云端表不修改。

官方说明：https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset。历史样本有脱敏占位值和内部一致性限制；来源是首次获客来源，金额是已记录USD购买金额。控制台如出现项目权限、配额或API未启用错误，保留错误文本再处理。
