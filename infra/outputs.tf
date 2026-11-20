output "project_id" {
  description = "CodeArts 项目 ID。"
  value       = huaweicloud_codearts_project.this.id
}

output "repository_id" {
  description = "CodeArts Repo 仓库 ID。"
  value       = huaweicloud_codearts_repository.this.repository_id
}

output "repository_url" {
  description = "CodeArts Repo HTTPS 地址。"
  value       = huaweicloud_codearts_repository.this.https_url
}

output "build_task_ids" {
  description = "四个 CodeArts Build 任务 ID。"
  value       = { for stage_name, task in huaweicloud_codearts_build_task.stage : stage_name => task.id }
}

output "pipeline_id" {
  description = "CodeArts Pipeline ID。"
  value       = huaweicloud_codearts_pipeline.this.id
}

output "toolchain_bucket_name" {
  description = "保存离线工具链与流水线状态的私有 OBS 桶名。"
  value       = huaweicloud_obs_bucket.toolchain.bucket
}

output "toolchain_object_keys" {
  description = "构建机下载的离线 Terraform 与 provider 对象键。"
  value = {
    terraform = local.terraform_object_key
    provider  = local.provider_object_key
  }
}

output "pipeline_state_object_keys" {
  description = "四阶段之间传递状态和执行计划的私有对象键。"
  value = {
    state = local.state_object_key
    plan  = local.plan_object_key
  }
}

output "sample_log_group_name" {
  description = "sample-infra 创建并在末阶段删除的 LTS 日志组名称。"
  value       = local.log_group_name
}

output "managed_resource_counts" {
  description = "预期 Terraform 受管资源数，不含 data source。"
  value = {
    root         = 11
    sample_infra = 1
  }
}
