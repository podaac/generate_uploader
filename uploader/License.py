# Standard imports
import time

# Third-party imports
import boto3
import botocore

class License:
    """A class that returns IDL licenses back into use.
    
    License removes uniquely identified license reservations for the current
    Generat workflow and adds those licenses back into the appriopriate dataset
    and floating parameters.
    
    Attributes
    ----------
    unique_id: int
        Identifies IDL licenses used by workflow in Parameter Store.
    prefix: str 
        Prefix for environment that Generate is executing in
    dataset: str
        Name of dataset that has been processed
    logger: logging.StreamHandler
        Logger object to use for logging statements
    
    Methods
    -------
    """
    
    def __init__(self, unique_id, prefix, dataset, logger):
        """
        Attributes
        ----------
        unique_id: int
            Identifies IDL licenses used by workflow in Parameter Store.
        prefix: str 
            Prefix for environment that Generate is executing in
        dataset: str
            Name of dataset that has been processed
        logger: logging.StreamHandler
            Logger object to use for logging statements
        """
        
        self.unique_id = unique_id
        self.prefix = prefix
        self.dataset = dataset
        self.logger = logger
        
    def return_licenses(self):
        """Returns IDL licenses that were in use by the current workflow execution.
        """
        
        ssm = boto3.client("ssm", region_name="us-west-2")
        try:
            # Get number of licenses that were used in the workflow
            dataset_lic = ssm.get_parameter(Name=f"{self.prefix}-idl-{self.dataset}-{self.unique_id}-lic")["Parameter"]["Value"]
            floating_lic = ssm.get_parameter(Name=f"{self.prefix}-idl-{self.dataset}-{self.unique_id}-floating")["Parameter"]["Value"]
            
            # Wait until no other process is updating license info
            retrieving_lic =  ssm.get_parameter(Name=f"{self.prefix}-idl-retrieving-license")["Parameter"]["Value"]
            while retrieving_lic == "True":
                self.logger.info("Watiing for license retrieval...")
                time.sleep(3)
                retrieving_lic =  ssm.get_parameter(Name=f"{self.prefix}-idl-retrieving-license")["Parameter"]["Value"]
            
            # Place hold on licenses so they are not changed
            self.hold_license(ssm, "True")  
            
            # Return licenses to appropriate parameters
            self.write_licenses(ssm, dataset_lic, floating_lic)
            
            # Release hold as done updating
            self.hold_license(ssm, "False")
            
            # Delete unique parameters
            response = ssm.delete_parameters(
                Names=[f"{self.prefix}-idl-{self.dataset}-{self.unique_id}-lic",
                       f"{self.prefix}-idl-{self.dataset}-{self.unique_id}-floating"]
            )
            self.logger.info(f"Deleted parameter: {self.prefix}-idl-{self.dataset}-{self.unique_id}-lic")
            self.logger.info(f"Deleted parameter: {self.prefix}-idl-{self.dataset}-{self.unique_id}-floating")
            
        except botocore.exceptions.ClientError as e:
            self.logger.error(e)
            self.logger.info("System exit.")
            exit(1)
    
    def hold_license(self, ssm, on_hold):
        """Put parameter license number ot use indicating retrieval in process."""
        
        try:
            response = ssm.put_parameter(
                Name=f"{self.prefix}-idl-retrieving-license",
                Type="String",
                Value=on_hold,
                Tier="Standard",
                Overwrite=True
            )
        except botocore.exceptions.ClientError as e:
            hold_action = "place" if on_hold == "True" else "remove"
            self.logger.error(f"Could not {hold_action} a hold on licenses...")
            raise e
        
    def write_licenses(self, ssm, dataset_lic, floating_lic):
        """Write license data to indicate number of licenses ready to be used."""
      
        try:
            response = ssm.put_parameter(
                Name=f"{self.prefix}-idl-{self.dataset}",
                Type="String",
                Value=str(dataset_lic),
                Tier="Standard",
                Overwrite=True
            )
            current_floating = ssm.get_parameter(Name=f"{self.prefix}-idl-floating")["Parameter"]["Value"]
            floating_total = int(floating_lic) + int(current_floating)
            response = ssm.put_parameter(
                Name=f"{self.prefix}-idl-floating",
                Type="String",
                Value=str(floating_total),
                Tier="Standard",
                Overwrite=True
            )
            self.logger.info(f"Wrote {dataset_lic} license(s) to {self.dataset}.")
            self.logger.info(f"Wrote {floating_lic} license(s)to floating.")
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"Could not return {self.dataset} and floating licenses...")
            raise e