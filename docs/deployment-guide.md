# 部署指南

本文给出从零到可验证部署的完整命令，每一步都附预期输出。
命令默认在本仓库根目录执行，需要进入子目录时会显式写出 `cd`。

架构与设计取舍见 [architecture.md](architecture.md)。

## 0. 约定与占位符

| 占位符 | 含义 | 取值方式 |
|-|-|-|
| `<HW_ACCESS_KEY>` | Access Key ID | 控制台「我的凭证」页面的访问密钥区域 |
| `<HW_SECRET_KEY>` | Secret Access Key | 同上；两者只填入当前 shell，不要写入代码或提交到仓库 |
| `<全局唯一桶名>` | 私有制品桶名 | 自行规划；须符合桶命名规则且全局唯一 |

## 1. 自检本地工具

```bash
python --version
terraform version
unzip -v | head -1
```

预期输出（版本不低于下表要求即可）：

```text
Python 3.11.9
Terraform v1.9.8
UnZip 6.00
```

要求：Terraform CLI `>= 1.9 且 < 2.0`，huaweicloud Provider `1.95.0`，
Python 3.9 及以上。

## 2. 静态校验

```bash
cd infra
terraform init
terraform validate
```

预期输出：

```text
Success! The configuration is valid, but there were some
validation warnings as shown above.
```

示例工程同样可以单独校验：

```bash
cd ../src/sample-infra
terraform init -backend=false -input=false
terraform validate
cd ../../infra
```

预期输出为 `Success!`。`-backend=false` 用于跳过后端初始化：示例资源的状态由流水线在桶内生成，
本地校验不需要也不应该产生状态。

## 3. 安全自检（可选）

```bash
python src/scripts/check_security.py
```

脚本检查仓库内是否存在误提交的凭据文件，不访问任何云端接口。

## 4. 配置访问凭据

```bash
export HW_ACCESS_KEY=<HW_ACCESS_KEY>
export HW_SECRET_KEY=<HW_SECRET_KEY>
```

## 5. 提供部署参数

必填两项：`bucket_name`、`ci_ak` 与 `ci_sk`。

```bash
export TF_VAR_bucket_name="<全局唯一桶名>"
export TF_VAR_ci_ak="<构建机访问密钥 ID>"
export TF_VAR_ci_sk="<构建机访问密钥 Secret>"
```

### 5.1 主要参数

| 变量 | 类型 | 默认值 | 必填 | 说明 |
|-|-|-|-|-|
| `region` | string | `cn-north-4` | 否 | 部署区域 |
| `prefix` | string | `tf-cicd-demo` | 否 | 资源名称前缀；小写字母开头，长度 3~32 |
| `bucket_name` | string | 无 | 是 | 私有制品桶名，全局唯一 |
| `repository_branch` | string | `master` | 否 | 仓库默认分支 |
| `ci_ak` / `ci_sk` | string | 无 | 是 | 构建机访问凭据（敏感） |
| `python_path` | string | `python` | 否 | 初始化仓库时使用的 Python 可执行文件 |
| `sample_log_ttl_days` | number | `1` | 否 | 示例日志组保留天数；取值 1~365 |

### 5.2 几处容易填错的位置

- `bucket_name` 必须全局唯一且符合桶命名规则，规划一次即可。
- `ci_ak` / `ci_sk` 会下发给构建机，仅用于访问本桶与服务接口，建议使用专用凭据。
- `sample_log_ttl_days` 只作用于示例日志组，不影响平台资源。

## 6. 创建平台资源

```bash
cd infra
terraform plan -out=cicd.tfplan
terraform apply cicd.tfplan
```

`terraform plan` 预期会创建以下资源：

```text
Plan: 11 to add, 0 to change, 0 to destroy.
```

构成：1 个项目、1 个仓库、4 个构建任务、1 条流水线、1 个私有桶、2 个桶对象。

`terraform apply` 完成后预期输出：

```text
Apply complete! Resources: 11 added, 0 changed, 0 destroyed.
```

应用收尾时会执行一次仓库初始化，把 `src/repository/README.md` 与 `src/sample-infra/` 下的
Terraform 文件提交到新建仓库。预期在应用输出中看到初始化完成的提示；
若这一步失败，可单独重跑（见第 10 节）。

## 7. 读取部署输出

```bash
terraform output
```

预期列出以下输出名：

```text
build_task_ids   managed_resource_counts   pipeline_id
project_id       repository_id             repository_url
sample_log_group_name                       toolchain_bucket_name
toolchain_object_keys                       pipeline_state_object_keys
```

常用取值：

```bash
terraform output repository_url            # 仓库地址
terraform output build_task_ids            # 四个构建任务 ID
terraform output toolchain_object_keys     # 构建机下载的工具链对象键
terraform output pipeline_state_object_keys  # 阶段间状态与计划对象键
```

## 8. 运行流水线

在流水线的控制台页面点击「运行」（该流水线只配置手动运行）。
四个阶段按序执行，每阶段的执行摘要可从构建任务页面展开。

预期行为：

- 校验阶段输出 `fmt -check` 与 `validate` 的结果，无输出即通过。
- 计划阶段在桶内生成 `pipeline-state/sample-infra.tfplan`。
- 应用阶段创建示例日志组，并把状态写回 `pipeline-state/sample-infra.tfstate`。
- 销毁阶段销毁示例日志组并删除计划与状态对象。

## 9. 验证部署

```bash
python src/scripts/verify_e2e.py
```

脚本触发并核对四阶段流水线，把阶段状态、标记行与删除确认写入 `verify-result.json`。
脚本不会执行 `terraform apply`，只读取部署输出并驱动流水线运行。

## 10. 手工验证示例

### 10.1 查看四个阶段的状态

```bash
terraform output -json build_task_ids
```

在构建任务页面分别打开最近一次执行记录，确认四个阶段均为成功。
阶段失败时构建日志会给出具体报错行。

### 10.2 核对桶内对象

```bash
export BUCKET="$(terraform output -raw toolchain_bucket_name)"
```

流水线运行完成后，桶内应保留两个工具链对象：

```text
toolchain/terraform_1.9.8_linux_amd64.zip
toolchain/terraform-provider-huaweicloud_1.95.0_linux_amd64.zip
```

销毁阶段结束后，`pipeline-state/` 下的计划与状态对象应被删除。

### 10.3 核对示例资源已按预期创建与清理

示例资源是名为 `<prefix>-pipeline-lts-group` 的日志组。应用阶段结束后可在日志服务控制台看到它；
销毁阶段结束后它应被删除。可直接取输出确认预期名称：

```bash
terraform output sample_log_group_name
```

### 10.4 重跑仓库初始化

若第 6 步的初始化未完成，可单独重跑：

```bash
python src/scripts/bootstrap_repo.py
```

预期输出提交成功的文件清单。脚本从仓库根目录读取 `src/repository/` 与 `src/sample-infra/`。

**部署完成后请按本节步骤在真实环境自行验证，确认功能可用后方可视为交付完成。**

## 11. 调整示例资源

示例资源的声明在 `src/sample-infra/`，改动后需要重新提交到仓库，流水线才会消费：

```bash
python src/scripts/bootstrap_repo.py
```

随后在流水线页面重新运行。

## 12. 释放资源

分两步。第一步由流水线完成，清理示例资源：

在流水线页面运行一次完整流水线（`destroy` 阶段会销毁示例日志组并清理状态对象）。

第二步清理平台资源：

```bash
cd infra
terraform destroy
```

预期输出：

```text
Destroy complete! Resources: 11 destroyed.
```

私有桶声明了 `force_destroy`，销毁时会连带清理桶内对象（含手动上传的文件）。

## 13. 故障排查

| 现象 | 定位方向 |
|-|-|
| 构建在准备工具链阶段失败 | 桶内是否存在 `toolchain/` 下的两个对象；对象键是否与 `terraform output toolchain_object_keys` 一致 |
| 构建报初始化失败 | 插件镜像目录层级是否与 `registry.terraform.io/huaweicloud/huaweicloud` 匹配；`-plugin-dir` 是否指对 |
| 构建机无权限 | 核对 `ci_ak` / `ci_sk` 是否具备桶读写与服务调用权限 |
| 计划阶段通过但应用阶段失败 | 检查计划对象是否已上传；应用阶段是否读到了同一份对象 |
| 销毁阶段报状态不存在 | 首次运行未走到应用阶段，属预期；状态对象在应用阶段才生成 |
| 仓库初始化失败 | 核对 `python_path` 与仓库 ID；凭据是否具备仓库写入权限 |
| 流水线未自动触发 | 属预期：流水线只配置手动运行，自动触发需在控制台单独开启 |
| 每次应用都提示构建步骤变更 | 检查是否改动了插件模块标识或步骤参数；版本号已让出所有权，不应产生差异 |
