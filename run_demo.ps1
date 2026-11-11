chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location $PSScriptRoot
$env:ECOM_OUTPUT = 'data/demo_build'
& .\.venv\Scripts\python.exe -m src.make_fixture
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m src.pipeline --config config/settings.demo.yml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m streamlit run app.py
