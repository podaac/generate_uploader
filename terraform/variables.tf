variable "app_name" {
  type        = string
  description = "Application name"
  default     = "generate"
}

variable "app_version" {
  type        = string
  description = "The application version number"
  default     = "0.1.4"
}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy to"
  default     = "us-west-2"
}

variable "cross_account_id" {
  type        = string
  description = "Cross account identifier for Cumulus Topic publication"
}

variable "cross_account_prefix" {
  type        = string
  description = "Cross account prefix for Cumulus Topic publication"
}

variable "default_tags" {
  type    = map(string)
  default = {}
}

variable "environment" {
  type        = string
  description = "The environment in which to deploy to"
}

variable "prefix" {
  type        = string
  description = "Prefix to add to all AWS resources as a unique identifier"
}

variable "sns_topic_email" {
  type        = string
  description = "Email to send SNS Topic messages to"
}
