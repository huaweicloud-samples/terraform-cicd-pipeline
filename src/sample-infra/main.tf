resource "huaweicloud_lts_group" "pipeline_sample" {
  group_name  = var.log_group_name
  ttl_in_days = var.ttl_in_days

  tags = {
    managed_by = "terraform"
    purpose    = "codearts-pipeline-sample"
  }
}
