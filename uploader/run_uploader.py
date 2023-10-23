"""run_uploader runs the Uploader class to upload L2P granules to S3 bucket.

Args:
[1] prefix: String Prefix for environment that Generate is executing in.
[2] job_index: Integer index for current job. Enter "-235" if running in AWS.
[3] data_dir: Path to directory that contains processor data.
[4] input_json: Path to input JSON file to determine data to upload.
[5] processing_type: String 'quicklook' or 'refined'.
[6] dataset: Name of dataset that has been processed.
[7] venue: Name of venue workflow is running in (e.g. sit, uat, ops)
[8] ingest: Whether or not to send a CNM message to trigger L2P granule ingest.
"""

# Standard imports 
import datetime
import logging
import os
import pathlib
import sys

# Local imports
from Uploader import Uploader

def run_uploader():
    
    start = datetime.datetime.now()
    
    # Command line arguments
    prefix = sys.argv[1]
    job_index = check_for_aws_batch_index(int(sys.argv[2]))
    data_dir = pathlib.Path(sys.argv[3])
    input_json = data_dir.joinpath("processor", "input", sys.argv[4])
    processing_type = sys.argv[5]
    dataset = sys.argv[6]
    venue = sys.argv[7]
    if len(sys.argv) > 8:
        ingest = True if sys.argv[8] == "true" else False
    else:
        ingest = True
        
    # Log information about current execution
    logger = get_logger()
    if dataset == "aqua":
        ds = "MODIS Aqua"
    elif dataset == "terra":
        ds = "MODIS Terra"
    else:
        ds = "VIIRS"
    logger.info(f"Job identifier: {os.environ.get('AWS_BATCH_JOB_ID')}")
    logger.info(f"Job index: {job_index}")
    logger.info(f"JSON file: {input_json.name}")
    logger.info(f"Dataset: {ds}")
    logger.info(f"Processing type: {processing_type.upper()}")
    
    # Upload L2P granules to S3 Bucket
    uploader = Uploader(prefix, job_index, input_json, data_dir, 
                        processing_type, dataset, logger, venue)
    uploader.upload(ingest)
    
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
    console_format = logging.Formatter("%(module)s - %(levelname)s : %(message)s")
    console_handler.setFormatter(console_format)

    # Add handlers to logger
    logger.addHandler(console_handler)

    # Return logger
    return logger
    
if __name__ == "__main__":
    run_uploader()