# upload

The upload component uploads the final L2P output of Generate to an S3 bucket and updates the Parameter Store to "return" the IDL licenses that were in used by workflow execution.

Top-level Generate repo: https://github.com/podaac/generate

## pre-requisites to building

None

## build command

`docker build --tag upload:0.1 . `

## execute command

Arguments:
1.	

MODIS A: 
`docker run --name gen-test -v /downloader/input:/data/input -v /downloader/logs:/data/logs -v /downloader/output:/data/output -v /downloader/scratch:/data/scratch downloader:0.1 /data/lists 0 L2 SPACE MODIS_A /data/output 5 1 yes yess`

MODIS T: 
`docker run --name gen-test -v /downloader/input:/data/input -v /downloader/logs:/data/logs -v /downloader/output:/data/output -v /downloader/scratch:/data/scratch downloader:0.1 /data/lists 0 L2 SPACE MODIS_T /data/output 5 1 yes yes`

VIIRS: 
`docker run --name gen-test -v /downloader/input:/data/input -v /downloader/logs:/data/logs -v /downloader/output:/data/output -v /downloader/scratch:/data/scratch downloader:0.1 /data/lists 0 L2 SPACE VIIRS /data/output 5 1 yes yes`

Please note that in order for the commands to execute the `/downloader/` directories will need to point to actual directories on the system.

## aws infrastructure

The downloader includes the following AWS services:
- AWS EFS
- AWS S3 bucket
- AWS SSM Parameter Store

## terraform 

Deploys AWS infrastructure and stores state in an S3 backend using a DynamoDB table for locking.

To deploy:
1. Edit `terraform.tfvars` for environment to deploy to.
2. Edit `terraform_conf/backed-{prefix}.conf` for environment deploy.
3. Initialize terraform: `terraform init -backend-config=terraform_conf/backend-{prefix}.conf`
4. Plan terraform modifications: `terraform plan -out=tfplan`
5. Apply terraform modifications: `terraform apply tfplan`

`{prefix}` is the account or environment name.