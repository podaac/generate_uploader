# Job Definition
resource "aws_batch_job_definition" "generate_batch_jd_uploader" {
  name                  = "${var.prefix}-uploader"
  type                  = "container"
  container_properties  = <<CONTAINER_PROPERTIES
  {
    "image": "${data.aws_ecr_repository.uploader.repository_url}:latest",
    "logConfiguration": {
        "logDriver" : "awslogs",
        "options": {
            "awslogs-group" : "${data.aws_cloudwatch_log_group.cw_log_group.name}"
        }
    },
    "mountPoints": [
        {
            "sourceVolume": "uploader",
            "containerPath": "/data",
            "readOnly": false
        }
    ],
    "resourceRequirements" : [
        { "type": "MEMORY", "value": "1024"},
        { "type": "VCPU", "value": "1024" }
    ],
    "volumes": [
        {
            "name": "uploader",
            "efsVolumeConfiguration": {
            "fileSystemId": "${data.aws_efs_file_system.aws_efs_generate.file_system_id}",
            "rootDirectory": "/processor"
            }
        }
    ],
    "jobRoleArn": "${aws_iam_role.aws_batch_job_role_uploader.arn}",
    "environment": [
      {
        "name": "TOPIC", "value": "${var.prefix}-upload-error"
      }
    ]
  }
  CONTAINER_PROPERTIES
  platform_capabilities = ["EC2"]
  propagate_tags        = true
  retry_strategy {
    attempts = 3
  }
}

# Cross account ID parameter
resource "aws_ssm_parameter" "aws_ssm_parameter_cumulus" {
  name        = "${var.prefix}-cumulus-account"
  description = "SNS Cumulus topic cross account identifier"
  type        = "SecureString"
  value       = var.cross_account_id
}

# Job role
resource "aws_iam_role" "aws_batch_job_role_uploader" {
  name = "${var.prefix}-batch-job-role-uploader"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "ecs-tasks.amazonaws.com"
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
  permissions_boundary = "arn:aws:iam::${local.account_id}:policy/NGAPShRoleBoundary"
}

resource "aws_iam_role_policy_attachment" "aws_batch_job_role_policy_attach" {
  role       = aws_iam_role.aws_batch_job_role_uploader.name
  policy_arn = aws_iam_policy.batch_job_role_policy_uploader.arn
}

resource "aws_iam_policy" "batch_job_role_policy_uploader" {
  name        = "${var.prefix}-batch-job-policy-uploader"
  description = "Provides access to: SNS, S3, EFS, SSM for uploader containers."
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "AllowListBucket",
        "Effect" : "Allow",
        "Action" : [
          "s3:ListBucket"
        ],
        "Resource" : "${data.aws_s3_bucket.l2p_granules.arn}"
      },
      {
        "Sid" : "AllowPutObject",
        "Effect" : "Allow",
        "Action" : [
          "s3:PutObject"
        ],
        "Resource" : "${data.aws_s3_bucket.l2p_granules.arn}/*"
      },
      {
        "Sid" : "AllowKMSKeyAccess",
        "Effect" : "Allow",
        "Action" : [
          "kms:GenerateDataKey"
        ],
        "Resource" : "${data.aws_kms_key.aws_s3.arn}"
      },
      {
        "Sid" : "AllowListTopics",
        "Effect" : "Allow",
        "Action" : [
          "sns:ListTopics"
        ],
        "Resource" : "*"
      },
      {
        "Sid" : "AllowPublishToTopic",
        "Effect" : "Allow",
        "Action" : [
          "sns:Publish"
        ],
        "Resource" : [
          "${aws_sns_topic.aws_sns_topic_upload_error.arn}",
          "arn:aws:sns:${var.aws_region}:${var.cross_account_id}:${var.cross_account_prefix}-throttled-provider-input-sns",
        ]
      },
      {
        "Sid" : "AllowGetParameter",
        "Effect" : "Allow",
        "Action" : [
          "ssm:GetParameter"
        ],
        "Resource" : "${aws_ssm_parameter.aws_ssm_parameter_cumulus.arn}"
      }
    ]
  })
}

# SNS topic for upload error
resource "aws_sns_topic" "aws_sns_topic_upload_error" {
  name         = "${var.prefix}-upload-error"
  display_name = "${var.prefix}-upload-error"
}

resource "aws_sns_topic_policy" "aws_sns_topic_upload_error_policy" {
  arn = aws_sns_topic.aws_sns_topic_upload_error.arn
  policy = jsonencode({
    "Version" : "2008-10-17",
    "Id" : "__default_policy_ID",
    "Statement" : [
      {
        "Sid" : "__default_statement_ID",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "*"
        },
        "Action" : [
          "SNS:GetTopicAttributes",
          "SNS:SetTopicAttributes",
          "SNS:AddPermission",
          "SNS:RemovePermission",
          "SNS:DeleteTopic",
          "SNS:Subscribe",
          "SNS:ListSubscriptionsByTopic",
          "SNS:Publish"
        ],
        "Resource" : "${aws_sns_topic.aws_sns_topic_upload_error.arn}",
        "Condition" : {
          "StringEquals" : {
            "AWS:SourceOwner" : "${local.account_id}"
          }
        }
      }
    ]
  })
}

resource "aws_sns_topic_subscription" "aws_sns_topic_upload_error_subscription" {
  endpoint  = var.sns_topic_email
  protocol  = "email"
  topic_arn = aws_sns_topic.aws_sns_topic_upload_error.arn
}