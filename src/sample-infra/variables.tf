variable "region" {
  description = "华为云区域。"
  type        = string
  default     = "cn-north-4"
}

variable "log_group_name" {
  description = "流水线创建并在末阶段删除的 LTS 日志组名称。"
  type        = string
}

variable "ttl_in_days" {
  description = "LTS 日志保留天数。"
  type        = number
  default     = 1

  validation {
    condition     = var.ttl_in_days >= 1 && var.ttl_in_days <= 365
    error_message = "ttl_in_days 必须在 1 到 365 之间。"
  }
}
