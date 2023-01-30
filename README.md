# uploader

The uploader component uploads the final L2P output of Generate to an S3 bucket and updates the Parameter Store to "return" the IDL licenses that were in use by the workflow execution.

Top-level Generate repo: https://github.com/podaac/generate

## pre-requisites to building

None

## build command

`docker build --tag uploader:0.1 . `

## execute command

Arguments:
1. unique_id: Integer to identify IDL licenses used by workflow in Parameter Store.
2. prefix: String Prefix for environment that Generate is executing in.
3. job_index: Integer index for current job. Enter "-235" if running in AWS.
4. last_job_index: Integer last AWS Batch upload job index. Enter "-1" for no index.
5. input_json: Path to input JSON file to determine data to upload.
6. data_dir: Path to directory that contains processor data.
7. processing_type: String 'quicklook' or 'refined'.
8. dataset: Name of dataset that has been processed.

MODIS A QUICKLOOK: 
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_AQUA_quicklook_2.json /data quicklook aqua`

MODIS A REFINED:
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_AQUA_refined_2.json /data refined aqua`

MODIS T QUICKLOOK: 
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_TERRA_quicklook_2.json /data quicklook terra`

MODIS T REFINED:
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_TERRA_refined_2.json /data refined terra`

VIIRS QUICKLOOK: 
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_VIIRS_quicklook_2.json /data quicklook viirs`

VIIRS REFINED:
`docker run --name upload --rm -e AWS_ACCESS_KEY_ID=$aws_key -e AWS_SECRET_ACCESS_KEY=$aws_secret -e AWS_DEFAULT_REGION=$default_region -v /uploader:/data uploader:latest 6233 podaac-sndbx-generate 0 -1 /data/input/processor_timestamp_list_VIIRS_refined_2.json /data refined viirs`

Please note that in order for the commands to execute the `/uploader/` directories will need to point to actual directories on the system.

## aws infrastructure

The downloader includes the following AWS services:
- AWS EFS
- AWS S3 bucket
- AWS SSM Parameter Store
- AWS SNS Topic

## terraform 

Deploys AWS infrastructure and stores state in an S3 backend using a DynamoDB table for locking.

To deploy:
1. Edit `terraform.tfvars` for environment to deploy to.
2. Edit `terraform_conf/backed-{prefix}.conf` for environment deploy.
3. Initialize terraform: `terraform init -backend-config=terraform_conf/backend-{prefix}.conf`
4. Plan terraform modifications: `terraform plan -out=tfplan`
5. Apply terraform modifications: `terraform apply tfplan`

`{prefix}` is the account or environment name.