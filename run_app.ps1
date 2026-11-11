chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:ECOM_OUTPUT = 'data/official_build'
& .\.venv\Scripts\python.exe -m streamlit run app.py
