variable "region" {
  description = "华为云区域。"
  type        = string
  default     = "cn-north-4"
}

variable "prefix" {
  description = "资源名称前缀。"
  type        = string
  default     = "tf-cicd-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.prefix))
    error_message = "prefix 必须以小写字母开头，只包含小写字母、数字和连字符，长度为 3 到 32。"
  }
}

variable "bucket_name" {
  description = "保存离线工具链和流水线状态的全局唯一私有 OBS 桶名。"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name 必须符合 OBS 桶 DNS 命名规则。"
  }
}

variable "repository_branch" {
  description = "CodeArts Repo 默认分支。"
  type        = string
  default     = "master"
}

variable "ci_ak" {
  description = "流水线构建机访问华为云 API 和私有 OBS 桶使用的访问密钥 ID。"
  type        = string
  sensitive   = true
}

variable "ci_sk" {
  description = "流水线构建机访问华为云 API 和私有 OBS 桶使用的秘密访问密钥。"
  type        = string
  sensitive   = true
}

variable "python_path" {
  description = "根工程 apply 后执行仓库初始化脚本的 Python 可执行文件路径。"
  type        = string
  default     = "python"
}

variable "sample_log_ttl_days" {
  description = "流水线创建的示例 LTS 日志组保留天数。"
  type        = number
  default     = 1

  validation {
    condition     = var.sample_log_ttl_days >= 1 && var.sample_log_ttl_days <= 365
    error_message = "sample_log_ttl_days 必须在 1 到 365 之间。"
  }
}
