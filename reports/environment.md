# 复现环境

Windows-11-10.0.26200-SP0；Python 3.13.5；Intel64 Family 6 Model 143 Stepping 8, GenuineIntel。

独立环境 .venv 从空目录创建，首次ensurepip失败后用宿主pip的--python安装到该环境。依赖锁定在requirements.txt，pip check通过。正式测试使用.venv解释器；TEMP/TMP指向项目内tests/runtime_tmp，避免系统沙盒临时目录访问限制。官方数据源与本地快照都可溯源，离线运行不依赖Google凭证。

Windows已实跑；macOS命令已提供，尚未在macOS实际验证。视频构建脚本使用Windows中文字体，仅该辅助脚本要求Windows字体路径。
