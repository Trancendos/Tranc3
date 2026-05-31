# infrastructure/opentofu/variables.tf
# Shared variable definitions for Trancendos OpenTofu configuration

variable "worker_ports" {
  description = "Port assignments for all Trancendos workers"
  type        = map(number)
  default = {
    infinity-ws            = 8004
    infinity-auth          = 8005
    users-service          = 8006
    monitoring             = 8007
    notifications          = 8008
    infinity-ai            = 8009
    the-grid               = 8010
    products-service       = 8011
    orders-service         = 8012
    payments-service       = 8013
    files-service          = 8014
    identity-service       = 8015
    analytics-service      = 8016
    audit-service          = 8017
    cache-service          = 8018
    cdn-service            = 8019
    config-service         = 8020
    cron-service           = 8021
    email-service          = 8022
    geo-service            = 8023
    search-service         = 8024
    sms-service            = 8025
    storage-service        = 8026
    queue-service          = 8027
    rate-limit-service     = 8028
    health-aggregator      = 8029
    gbrain-bridge          = 8030
    topology-service       = 8031
    ledger-service         = 8032
    model-router-service   = 8033
    workflow-engine-service = 8034
    skills-benchmark-service = 8035
    langchain-integration-service = 8036
    deepagents-orchestrator-service = 8037
    vault-service          = 8038
    blender-worker         = 8050
    triposr-worker         = 8051
    ffmpeg-worker          = 8052
  }
}

variable "resource_limits" {
  description = "Default resource limits for workers"
  type = object({
    cpu_limit    = string
    memory_limit = string
  })
  default = {
    cpu_limit    = "0.5"
    memory_limit = "256m"
  }
}
