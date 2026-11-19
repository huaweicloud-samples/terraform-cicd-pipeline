locals {
  # Repository root: one level above this Terraform configuration directory.
  repo_root = abspath("${path.module}/..")

  stage_order = ["validate", "plan", "apply", "destroy"]

  stage_labels = {
    validate = "Validate"
    plan     = "Plan"
    apply    = "Apply"
    destroy  = "Destroy"
  }

  stage_identifiers = {
    validate = "stage_validate"
    plan     = "stage_plan"
    apply    = "stage_apply"
    destroy  = "stage_destroy"
  }

  job_identifiers = {
    validate = "JOB_validate"
    plan     = "JOB_plan"
    apply    = "JOB_apply"
    destroy  = "JOB_destroy"
  }

  step_identifiers = {
    validate = "step_build_validate"
    plan     = "step_build_plan"
    apply    = "step_build_apply"
    destroy  = "step_build_destroy"
  }

  terraform_object_key = "toolchain/terraform_1.9.8_linux_amd64.zip"
  provider_object_key  = "toolchain/terraform-provider-huaweicloud_1.95.0_linux_amd64.zip"
  state_object_key     = "pipeline-state/sample-infra.tfstate"
  plan_object_key      = "pipeline-state/sample-infra.tfplan"
  log_group_name       = "${var.prefix}-pipeline-lts-group"

  repository_files = {
    "repository/README.md"      = "README.md"
    "sample-infra/versions.tf"  = "sample-infra/versions.tf"
    "sample-infra/main.tf"      = "sample-infra/main.tf"
    "sample-infra/variables.tf" = "sample-infra/variables.tf"
    "sample-infra/outputs.tf"   = "sample-infra/outputs.tf"
  }

  repository_payload_hash = sha256(join("", [
    for source_path in sort(keys(local.repository_files)) :
    "${local.repository_files[source_path]}:${filesha256("${path.module}/../src/${source_path}")}"
  ]))
}
