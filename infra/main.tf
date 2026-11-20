resource "huaweicloud_obs_bucket" "toolchain" {
  bucket        = var.bucket_name
  storage_class = "STANDARD"
  acl           = "private"
  force_destroy = true

  tags = {
    managed_by = "terraform"
    purpose    = "codearts-terraform-cicd"
  }
}

resource "huaweicloud_obs_bucket_object" "terraform_cli" {
  bucket       = huaweicloud_obs_bucket.toolchain.bucket
  key          = local.terraform_object_key
  source       = "${path.module}/../src/dist/terraform_1.9.8_linux_amd64.zip"
  content_type = "application/zip"
  etag         = filemd5("${path.module}/../src/dist/terraform_1.9.8_linux_amd64.zip")
}

resource "huaweicloud_obs_bucket_object" "huaweicloud_provider" {
  bucket       = huaweicloud_obs_bucket.toolchain.bucket
  key          = local.provider_object_key
  source       = "${path.module}/../src/dist/terraform-provider-huaweicloud_1.95.0_linux_amd64.zip"
  content_type = "application/zip"
  etag         = filemd5("${path.module}/../src/dist/terraform-provider-huaweicloud_1.95.0_linux_amd64.zip")
}

resource "huaweicloud_codearts_project" "this" {
  name        = "${var.prefix}-project"
  type        = "scrum"
  description = "Terraform 基础设施四阶段流水线示例"
}

resource "huaweicloud_codearts_repository" "this" {
  project_id       = huaweicloud_codearts_project.this.id
  name             = "${var.prefix}-repo"
  description      = "Terraform 基础设施定义仓库"
  enable_readme    = 1
  import_members   = 0
  visibility_level = 0
}

resource "huaweicloud_codearts_build_task" "stage" {
  for_each = toset(local.stage_order)

  project_id = huaweicloud_codearts_project.this.id
  name       = "${var.prefix}-${each.key}-build"
  arch       = "x86-64"

  scms {
    url       = huaweicloud_codearts_repository.this.ssh_url
    scm_type  = "codehub"
    web_url   = huaweicloud_codearts_repository.this.web_url
    repo_id   = huaweicloud_codearts_repository.this.repository_id
    repo_name = huaweicloud_codearts_repository.this.name
    branch    = var.repository_branch
  }

  steps {
    enable    = true
    module_id = "devcloud2018.codeci_action_20017.action"
    name      = "Terraform ${local.stage_labels[each.key]}"

    properties = {
      image        = jsonencode("shell4.2.46-git1.8.3-zip6.00")
      preCondition = jsonencode("SUCCESS")
      command = jsonencode(templatefile("${path.module}/../src/templates/build_stage.sh.tftpl", {
        stage                = each.key
        region               = var.region
        bucket               = huaweicloud_obs_bucket.toolchain.bucket
        terraform_object_key = local.terraform_object_key
        provider_object_key  = local.provider_object_key
        state_object_key     = local.state_object_key
        plan_object_key      = local.plan_object_key
        log_group_name       = local.log_group_name
        ttl_in_days          = var.sample_log_ttl_days
        ci_ak                = var.ci_ak
        ci_sk                = var.ci_sk
      }))
    }
  }

  depends_on = [
    huaweicloud_obs_bucket_object.terraform_cli,
    huaweicloud_obs_bucket_object.huaweicloud_provider,
  ]
}

resource "huaweicloud_codearts_pipeline" "this" {
  project_id  = huaweicloud_codearts_project.this.id
  name        = "${var.prefix}-pipeline"
  description = "依次执行 Terraform Validate、Plan、Apply 和 Destroy"
  is_publish  = false

  sources {
    type = "code"

    params {
      git_type       = "codehub"
      codehub_id     = huaweicloud_codearts_repository.this.repository_id
      default_branch = var.repository_branch
      git_url        = huaweicloud_codearts_repository.this.https_url
      ssh_git_url    = huaweicloud_codearts_repository.this.ssh_url
      web_url        = huaweicloud_codearts_repository.this.web_url
      repo_name      = huaweicloud_codearts_repository.this.name
    }
  }

  concurrency_control {
    concurrency_number = 1
    exceed_action      = "QUEUE"
    enable             = true
  }

  definition = jsonencode({
    stages = [
      for stage_name in local.stage_order : {
        name          = local.stage_labels[stage_name]
        identifier    = local.stage_identifiers[stage_name]
        run_condition = null
        type          = null
        sequence      = index(local.stage_order, stage_name)
        parallel      = null
        pre = [
          {
            runtime_attribution   = null
            multi_step_editable   = 0
            official_task_version = null
            icon_url              = null
            name                  = null
            task                  = "official_devcloud_autoTrigger"
            business_type         = null
            inputs                = null
            env                   = null
            sequence              = 0
            identifier            = null
            endpoint_ids          = null
          }
        ]
        post = null
        jobs = [
          {
            id             = ""
            identifier_old = null
            stage_index    = null
            type           = null
            name           = "Terraform_${local.stage_labels[stage_name]}"
            async          = null
            identifier     = local.job_identifiers[stage_name]
            sequence       = 0
            condition      = "$${{ default() }}"
            strategy       = null
            timeout        = ""
            resource       = "{\"type\":\"system\",\"arch\":\"x86\"}"
            steps = [
              {
                runtime_attribution   = "agent"
                multi_step_editable   = 0
                official_task_version = "0.0.7"
                icon_url              = null
                name                  = "Build_${local.stage_labels[stage_name]}"
                task                  = "official_devcloud_cloudBuild"
                business_type         = "Build"
                inputs = [
                  { key = "__sameProject__", value = "true" },
                  { key = "__projectId__", value = "" },
                  { key = "jobId", value = huaweicloud_codearts_build_task.stage[stage_name].id },
                  { key = "__repository__", value = "" },
                  { key = "artifactIdentifier", value = "" },
                ]
                env          = []
                sequence     = 0
                identifier   = local.step_identifiers[stage_name]
                endpoint_ids = []
              }
            ]
            unfinished_steps = []
            condition_tag    = ""
            exec_type        = null
            depends_on       = []
            reusable_job_id  = null
          }
        ]
        depends_on = []
        run_always = false
      }
    ]
  })
}

resource "terraform_data" "bootstrap_repository" {
  triggers_replace = [local.repository_payload_hash]

  provisioner "local-exec" {
    command = "${var.python_path} ${local.repo_root}/scripts/bootstrap_repo.py"

    environment = {
      PYTHONIOENCODING = "utf-8"
      HW_ACCESS_KEY    = var.ci_ak
      HW_SECRET_KEY    = var.ci_sk
      REGION           = var.region
      REPOSITORY_ID    = huaweicloud_codearts_repository.this.repository_id
      REPOSITORY_ROOT  = local.repo_root
      TARGET_BRANCH    = var.repository_branch
    }
  }

  depends_on = [huaweicloud_codearts_pipeline.this]
}
