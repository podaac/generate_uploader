# Standard imports
import datetime
import json
import os
import pathlib

# Third-part imports
import boto3
import botocore

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
            "filename_suffix": "TS-JPL-L2P_GHRSST-SSTskin-MODIS_T-T-v02.0-fv01.0",
        },
        "viirs": {
            "dirname0": "VIIRS_L2P_CORE_NETCDF",
            "dirname1": "VIIRS",
            "filename_suffix": "TS-JPL-L2P_GHRSST-SSTskin-VIIRS_NPP-T-v02.0-fv01.0",
        }
    }
    
    def __init__(self, prefix, job_index, last_job_index, \
                 input_json, data_dir, processing_type, dataset, logger):
        """
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
        """
        
        self.prefix = prefix
        self.job_index = job_index
        self.last_job_index = last_job_index
        self.input_json = input_json
        self.data_dir = data_dir
        self.processing_type = processing_type
        self.dataset = dataset
        self.logger = logger
        
    def upload(self):
        """Upload L2P granule files found in EFS processor output directory."""
        
        l2p_list, error_list = self.load_efs_l2p()
        error_list = self.upload_l2p_s3(l2p_list, error_list)  
        if len(error_list) > 0: self.report_errors(error_list)         
        
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
            l2p_dir = self.data_dir.joinpath("output", 
                                             dataset_dict["dirname0"],
                                             dataset_dict["dirname1"],
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
                else:
                    missing_checksum.append(night_file_nc)
                
        return l2p_list, missing_checksum
    
    def upload_l2p_s3(self, l2p_list, error_list):
        """Upload L2P granule files to S3 bucket."""
        
        s3_client = boto3.client("s3")
        bucket = f"{self.prefix}-l2p-granules"
    
        for l2p in l2p_list:
            try:
                response = s3_client.upload_file(str(l2p), bucket, l2p.name, ExtraArgs={"ServerSideEncryption": "aws:kms"})
                self.logger.info(f"File uploaded: {l2p.name}")
                
            except botocore.exceptions.ClientError as e:
                self.logger.error(e)
                error_list.append(l2p)
                
        return error_list
    
    def report_errors(self, error_list):
        """Report on files that could not be uploaded.
        
        Logs to CloudWatch and sends an SNS Topic notification.
        """
        
        # Log files
        self.logger.error("The following files failed to upload...")
        for error_file in error_list:
            self.logger.error(error_file)
            
        # Send notification
        sns = boto3.client("sns")
        try:
            # Locate topic
            topics = sns.list_topics()
            topic = list(filter(lambda x: (os.environ.get("TOPIC") in x["TopicArn"]), topics["Topics"]))
            
            # Publich message    
            subject = f"UPLOADER: S3 upload file failure: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
            errors = [ str(error_file) for error_file in error_list ]
            message = f"The following L2P granule files failed to upload...\n" \
                + "\n".join(errors)
            response = sns.publish(
                TopicArn = topic[0]["TopicArn"],
                Message = message,
                Subject = subject
            )
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"Failed to publish to SNS Topic: {topic[0]['TopicArn']}")
            self.logger.error(f"Error - {e}")
            self.logger.info(f"System exit.")
            exit(1)
        
        self.logger.info(f"Message published to SNS Topic: {topic[0]['TopicArn']}")