output "log_group_id" {
  description = "LTS 日志组 ID。"
  value       = huaweicloud_lts_group.pipeline_sample.id
}

output "log_group_name" {
  description = "LTS 日志组名称。"
  value       = huaweicloud_lts_group.pipeline_sample.group_name
}
