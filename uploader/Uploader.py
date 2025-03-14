# Standard imports
import datetime
import hashlib
import json
import os
import sys

# Third-part imports
import boto3
import botocore
import requests

class Uploader:
    """A class that uploads final L2P granules to an S3 bucket.
    
    Upload locates the L2P granule file produced from the 'processor' component.
    It also releases any IDL licenses that werein use by the Generate workflow.
    
    Attributes
    ----------
    prefix: str 
            Prefix for environment that Generate is executing in
    job_index: int
        Index for current job, -235 indicates AWS Batch job
    last_job_index: int 
        Last AWS Batch upload job index. Enter "-1" for no index
    input_json: str
        Path to input JSON file to determine data to upload
    data_dir: pathlib.Path
        Path to directory that contains processor data
    processing_type: str
        'quicklook' or 'refined'
    dataset: str
        Name of dataset that has been processed
    logger: logging.StreamHandler
        Logger object to use for logging statements
    
    Methods
    -------
    upload():
        Upload L2P granule files found in EFS processor output directory
    load_efs_l2p():
        Load a list of L2P granules from EFS that have been processed
    upload_l2p_s3(self, l2p_list, error_list)
        Upload L2P granule files to S3 bucket
    report_errors(self, error_list)
        Report on files that could not be uploaded
    """
    
    # Constants
    DATA_DICT = {
        "aqua": {
            "dirname0": "MODIS_L2P_CORE_NETCDF",
            "dirname1": "MODIS_A",
            "filename": "TS-JPL-L2P_GHRSST-SSTskin-MODIS_A-T-v02.0-fv01.0",
        },
        "terra": {
            "dirname0": "MODIS_L2P_CORE_NETCDF",
            "dirname1": "MODIS_T",
            "filename": "TS-JPL-L2P_GHRSST-SSTskin-MODIS_T-T-v02.0-fv01.0",
        },
        "viirs": {
            "dirname0": "VIIRS_L2P_CORE_NETCDF",
            "dirname1": "VIIRS",
            "filename": "TS-JPL-L2P_GHRSST-SSTskin-VIIRS_NPP-T-v02.0-fv01.0",
        }
    }
    VERSION = "1.4"
    PROVIDER = "NASA/JPL/PO.DAAC"
    COLLECTION = {
        "aqua": "MODIS_A-JPL-L2P-v2019.0",
        "terra": "MODIS_T-JPL-L2P-v2019.0",
        "viirs": "VIIRS_NPP-JPL-L2P-v2016.2"
    }
    COMBINER_PREFIX = "combiner_file_lists_"
    PROCESSOR_PREFIX = "processor_timestamp_list_"
    
    def __init__(self, prefix, job_index, input_json, data_dir, processing_type,
                 dataset, logger, venue):
        """
        Attributes
        ----------
        prefix: str 
            Prefix for environment that Generate is executing in
        job_index: int
            Index for current job, -235 indicates AWS Batch job
        input_json: str
            Path to input JSON file to determine data to upload
        data_dir: pathlib.Path
            Path to directory that contains processor data
        processing_type: str
            'quicklook' or 'refined'
        dataset: str
            Name of dataset that has been processed
        logger: logging.StreamHandler
            Logger object to use for logging statements
        venue: str
            Name of venue workflow is running in (e.g. sit, uat, ops)
        """
        
        self.prefix = prefix
        self.job_index = job_index
        self.input_json = input_json
        self.data_dir = data_dir
        self.processing_type = processing_type
        self.dataset = dataset
        self.logger = logger
        self.cumulus_topic = f"podaac-{venue}-cumulus-provider-input-sns"
        self.cross_account = self.get_cross_account_id(prefix)
        self.processed = []
        self.provenance = []
        self.num_uploaded = 0
        
    def get_cross_account_id(self, prefix):
        """Return cross account identifier from SSM parameter store."""
        
        try:
            ssm_client = boto3.client('ssm', region_name="us-west-2")
            cross_account = ssm_client.get_parameter(Name=f"{prefix}-cumulus-account", WithDecryption=True)["Parameter"]["Value"]
        except botocore.exceptions.ClientError as error:
            self.logger.info(f"Failed to obtain cross account identifier for Cumulus topic.")
            self.logger.error(f"Error - {error}")
            self.logger.info(f"System exit.")
            sys.exit(1)
        
        return cross_account
        
    def upload(self, ingest):
        """Upload L2P granule files found in EFS processor output directory."""
        
        errors = {}
        l2p_list, errors["missing_checksum"] = self.load_efs_l2p()
        if len(l2p_list) == 0:
            self.logger.info(f"Did not locate any L2P granules.")
        else:
            l2p_s3, errors["upload"] = self.upload_l2p_s3(l2p_list)
            count = len([l2p for l2p in l2p_s3 if "md5" not in l2p])
            self.logger.info(f"Number of granules uploaded: {count}")
            self.num_uploaded = count
            sns = boto3.client("sns", region_name="us-west-2")
            if ingest:  
                errors["publish"] = self.publish_cnm_message(sns, l2p_s3)
            else:
                errors["publish"] = []
                self.logger.info("CNM message was not sent and L2P granules will not be ingested.")
            error_count = len(errors["missing_checksum"]) + len(errors["upload"]) + len(errors["publish"])
            if error_count > 0: 
                log_metadata = get_ecs_task_metadata(self.logger)
                self.report_errors(sns, log_metadata, errors)
            self.log_provenance(l2p_list)
        
    def load_efs_l2p(self):
        """Load a list of L2P granules from EFS that have been processed."""
        
        # Load time stamps
        with open(self.input_json) as jf:
            timestamps = json.load(jf)[self.job_index]
        
        # Build path to possible output file(s)
        dataset_dict = self.DATA_DICT[self.dataset]
        dirname1 = dataset_dict["dirname1"] if self.processing_type == "quicklook" else f"{dataset_dict['dirname1']}_REFINED"
        l2p_list = []
        missing_checksum = []    # Maintain a list of files with missing checksums
        for timestamp in timestamps:
            ts = timestamp.replace("T", "")
            time_str = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")      
            l2p_dir = self.data_dir.joinpath("processor",
                                             "output", 
                                             dataset_dict["dirname0"],
                                             dirname1,
                                             str(time_str.year),
                                             str(time_str.timetuple().tm_yday))
            
            file = f"{dataset_dict['filename'].replace('TS', ts)}"
            # Check for day file
            day_file = file.replace('-T-', '-D-')
            day_file_nc = l2p_dir.joinpath(f"{day_file}.nc")
            if day_file_nc.is_file():
                checksum = l2p_dir.joinpath(f"{day_file_nc}.md5")
                if checksum.is_file():
                    l2p_list.append(day_file_nc)
                    l2p_list.append(checksum)
                    self.logger.info(f"Located Day File: {day_file_nc}")
                else:
                    missing_checksum.append(day_file_nc)
            # Check for night file
            night_file = file.replace('-T-', '-N-')
            night_file_nc = l2p_dir.joinpath(f"{night_file}.nc")
            if night_file_nc.is_file():
                checksum = l2p_dir.joinpath(f"{night_file_nc}.md5")
                if checksum.is_file():
                    l2p_list.append(night_file_nc)
                    l2p_list.append(checksum)
                    self.logger.info(f"Located Night File: {night_file_nc}")
                else:
                    missing_checksum.append(night_file_nc)
                
        return l2p_list, missing_checksum
    
    def upload_l2p_s3(self, l2p_list):
        """Upload L2P granule files to S3 bucket."""
        
        s3_client = boto3.client("s3")
        bucket = f"{self.prefix}-l2p-granules"

        l2p_s3 = []
        error_list = []
        for l2p in l2p_list:
            try:
                response = s3_client.upload_file(str(l2p), bucket, f"{self.dataset}/{l2p.name}", ExtraArgs={"ServerSideEncryption": "AES256"})
                l2p_s3.append(f"s3://{bucket}/{self.dataset}/{l2p.name}")
                self.logger.info(f"File uploaded: s3://{bucket}/{self.dataset}/{l2p.name}.")
                if "md5" not in l2p.name: self.logger.info(f"Processed: {l2p.name}")
                if "md5" not in l2p.name: self.processed.append(l2p.name)
            except botocore.exceptions.ClientError as e:
                self.logger.error(f"Error encoutered: {e}.")
                error_list.append(l2p)
                
        return l2p_s3, error_list
    
    def publish_cnm_message(self, sns, l2p_s3):
        """Publish CNM message to kick off granule ingestion."""
        
        publish_errors = []
        for l2p in l2p_s3:
            if ".md5" in l2p: continue   # Skip md5 files
            message = self.create_message(l2p)
            errors = self.publish_message(sns, message)
            if len(errors) > 0: publish_errors.extend(errors)
            
        return publish_errors
            
    def create_message(self, l2p):
        """Create message to be published."""
        
        # Locate file on EFS
        filename = l2p.split('/')[4].split('.nc')[0]
        dataset_dict = self.DATA_DICT[self.dataset]
        dirname1 = dataset_dict["dirname1"] if self.processing_type == "quicklook" else f"{dataset_dict['dirname1']}_REFINED"
        ts = filename.split('-')[0]
        time_str = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")      
        l2p_dir = self.data_dir.joinpath("processor",
                                         "output", 
                                         dataset_dict["dirname0"],
                                         dirname1,
                                         str(time_str.year),
                                         str(time_str.timetuple().tm_yday))        
        # Build message
        message = {
            "version": self.VERSION,
            "provider": self.PROVIDER,
            "collection": self.COLLECTION[self.dataset],
            "submissionTime": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "identifier": filename,
            "product": {
                "name": filename,
                "files": [{
                    "uri": l2p,
                    "checksum": self.get_checksum(l2p_dir.joinpath(f"{filename}.nc")),
                    "size": os.stat(l2p_dir.joinpath(f"{filename}.nc")).st_size,
                    "type": "data",
                    "name": f"{filename}.nc",
                    "checksumType": "md5"
                }, {
                    "uri": f"{l2p}.md5",
                    "checksum": self.get_checksum(l2p_dir.joinpath(f"{filename}.nc.md5")),
                    "size": os.stat(l2p_dir.joinpath(f"{filename}.nc.md5")).st_size,
                    "type": "metadata",
                    "name": f"{filename}.nc.md5",
                    "checksumType": "md5"
                }],
                "dataVersion": self.COLLECTION[self.dataset].split('-')[-1].split('v')[-1]
            },
            "trace": self.prefix
        }
        
        return message
        
    def get_checksum(self, l2p_path):
        """Return checksum for file contents."""
        
        with open(l2p_path, "rb") as f:
            bytes = f.read()
            checksum = hashlib.md5(bytes).hexdigest()
        return checksum
    
    def publish_message(self, sns, message):
        """Publish message to Cumulus topic."""
        
        # Send notification
        errors = []
        try:
            response = sns.publish(
                TopicArn = f"arn:aws:sns:us-west-2:{self.cross_account}:{self.cumulus_topic}",
                Message = json.dumps(message),
            )
            self.logger.info(f"{message['identifier']} message published to SNS Topic: {self.cumulus_topic}")
        except botocore.exceptions.ClientError as e:
            self.logger.info(f"Failed to publish {message['identifier']} to SNS Topic: {self.cumulus_topic}")
            self.logger.error(e)
            errors.append(message['identifier'])
        
        return errors
    
    def report_errors(self, sns, log_metadata, error_list):
        """Report on files that could not be uploaded.
        
        Logs to CloudWatch and sends an SNS Topic notification.
        """
        
        # Create message and log errors
        message = f"Uploader AWS Batch job L2P granule failures for {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}."
        
        message += "\n\nJOB INFORMATION:\n"
        message += f"Job Identifier: {os.environ.get('AWS_BATCH_JOB_ID')}\n"
        message += f"Job Queue: {os.environ.get('AWS_BATCH_JQ_NAME')}"
        
        if log_metadata:
            message += "\n\n" + log_metadata
            
        message += f"\n\nERROR INFORMATION:"
        
        missing_errors = []
        for error_file in error_list["missing_checksum"]:
            missing_errors.append(str(error_file))
            self.logger.error(f"Missing checksum file: {error_file}")
        if len(missing_errors) > 0:
            message = f"\nThe following L2P granule files are missing checksums...\n" \
                + "\n".join(missing_errors)
        
        upload_errors = []
        for error_file in error_list["upload"]:
            upload_errors.append(str(error_file))
            self.logger.info(f"Failed to upload to S3: {error_file}")
        if len(upload_errors) > 0:
            message += f"\nThe following L2P granule files failed to upload to S3 bucket...\n" \
            + "\n".join(upload_errors)
        
        publish_errors = []
        for error_file in error_list["publish"]:
            publish_errors.append(error_file)
            self.logger.info(f"Failed to publish to cumulus topic: {error_file}")
        if len(publish_errors) > 0:
            message += f"\nThe following L2P granule NetCDF and checksum files failed to be published to the Cumulus Topic...\n" \
            + "\n".join(publish_errors)
            
        message += "\n\nPlease follow these steps to diagnose the error: https://wiki.jpl.nasa.gov/pages/viewpage.action?pageId=771470900#GenerateCloudErrorDetection&Recovery-AWSBatchJobFailures\n\n\n"
        
        # Send notification
        try:
            topics = sns.list_topics()
            topic = list(filter(lambda x: (os.environ.get("TOPIC") in x["TopicArn"]), topics["Topics"]))
            subject = "Generate workflow error: UPLOADER error"
            response = sns.publish(
                TopicArn = topic[0]["TopicArn"],
                Message = message,
                Subject = subject
            )
        except botocore.exceptions.ClientError as e:
            self.logger.info(f"Failed to publish to SNS Topic: {topic[0]['TopicArn']}")
            self.logger.error(f"Error - {e}")
            self.logger.info(f"System exit.")
            sys.exit(1)
        
        self.logger.info(f"Message published to SNS Topic: {topic[0]['TopicArn']}")
        sys.exit(1)
        
    def log_provenance(self, l2p_list):
        """Log provenance of each L2P granule."""
        
        # Load combiner JSON from process JSON file name
        combiner_json = self.input_json.name.replace(self.PROCESSOR_PREFIX, self.COMBINER_PREFIX)
        with open(self.data_dir / "combiner" / "downloads" / combiner_json) as jf:
            sst_files = json.load(jf)[self.job_index]
        
        # Determine which SST files created the L2P granules
        for l2p in l2p_list:
            if "md5" in l2p.name: continue
            ts = l2p.name.split('-')[0]
            timestamp = f"{ts[0:8]}T{ts[8:]}"
            provenance = list(filter(lambda e: (timestamp in e), sst_files))
            self.logger.info(f"Provenance: {l2p.name} | {', '.join(provenance)}")
            self.provenance.append(f"{l2p.name} | {'; '.join(provenance)}")

def get_ecs_task_metadata(logger):
    """Return log group and log stream if available from ECS task endpoint."""
    
    ecs_endpoint = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
    if ecs_endpoint:
        response = requests.get(ecs_endpoint)
        logger.info(f"ECS endpoint response: {response}.")
        response_json = response.json()
        log_group = response_json["LogOptions"]["awslogs-group"]
        log_stream = response_json["LogOptions"]["awslogs-stream"]
        log = f"Log Group: {log_group}\nLog Stream: {log_stream}"
    else:
        log = ""
    return log