"""run_uploader runs the Uploader class with the appropriate data.

run_uploader coordinates the operations of the Uploader class and recieves a
unique identifier, prefix, and the last AWS Batch job index from the caller.

The last job index determines if IDL licenses should be made available for
subsequent executions of the Generate workflow.

Args:
[1] unique_id: Integer to identify IDL licenses used by workflow in Parameter Store.
[2] prefix: String Prefix for environment that Generate is executing in.
[3] job_index: Integer index for current job. Enter "-235" if running in AWS.
[4] last_job_index: Integer last AWS Batch upload job index. Enter "-1" for no index.
[5] input_json: Path to input JSON file to determine data to upload.
[6] data_dir: Path to directory that contains processor data.
[7] processing_type: String 'quicklook' or 'refined'.
[8] dataset: Name of dataset that has been processed.


'job_index' should be set to -235 for AWS executions or not set at all if a job is executed as a single job and not a job array.
'last_job_index' is used to determine if this is the last AWS Batch job to execute and therefore the IDL licenses need to be returned for the next execution of the workflow. -1 should be entered for single (non-array) jobs.
"""

# Standard imports 
import datetime
import logging
import os
import pathlib
import sys

# Local imports
from License import License
from Uploader import Uploader

def run_uploader():
    
    start = datetime.datetime.now()
    
    # Command line arguments
    unique_id = int(sys.argv[1])
    prefix = sys.argv[2]
    job_index = check_for_aws_batch_index(int(sys.argv[3]))
    last_job_index = int(sys.argv[4])
    input_json = pathlib.Path(sys.argv[5])
    data_dir = pathlib.Path(sys.argv[6])
    processing_type = sys.argv[7]
    dataset = sys.argv[8]
    
    # Uplad L2P granules to S3 Bucket
    logger = get_logger()
    uploader = Uploader(prefix, job_index, last_job_index, \
                        input_json, data_dir, processing_type, dataset, logger)
    uploader.upload()   
    
    # Return IDL licenses if single or last job
    batch_job_index = int(os.environ.get("AWS_BATCH_JOB_ARRAY_INDEX")) if os.environ.get("AWS_BATCH_JOB_ARRAY_INDEX") is not None else -1
    if last_job_index == -1 or last_job_index == batch_job_index:
        license = License(unique_id, prefix, dataset, logger)
        license.return_licenses()
    
    end = datetime.datetime.now()
    logger.info(f"Total execution time: {end - start}")

def check_for_aws_batch_index(job_index):
    """Deterime if running as an AWS Batch job array with an index."""
    
    i = job_index if job_index != -235 else int(os.environ.get("AWS_BATCH_JOB_ARRAY_INDEX"))
    return i

def get_logger():
    """Return a formatted logger object."""
    
    # Remove AWS Lambda logger
    logger = logging.getLogger()
    for handler in logger.handlers:
        logger.removeHandler(handler)
    
    # Create a Logger object and set log level
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Create a handler to console and set level
    console_handler = logging.StreamHandler()

    # Create a formatter and add it to the handler
    console_format = logging.Formatter("%(asctime)s - %(module)s - %(levelname)s : %(message)s")
    console_handler.setFormatter(console_format)

    # Add handlers to logger
    logger.addHandler(console_handler)

    # Return logger
    return logger
    
if __name__ == "__main__":
    run_uploader()