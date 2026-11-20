# Terraform 基础设施流水线仓库

本仓库由 CodeArts Pipeline 检出。流水线依次执行配置校验、执行计划、资源创建和资源清理。

`sample-infra/` 只声明一个 LTS 日志组。资源创建阶段建立该日志组，资源清理阶段删除该日志组。

Terraform 与 huaweicloud provider 均由构建任务从私有 OBS 桶下载，构建机无需预装 Terraform，也不访问公共 provider 注册中心。
