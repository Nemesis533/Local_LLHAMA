import sys
import os
from .Shared_Logger import shared_logger, LogLevel
from .Runtime_Supervisor import LocalLLHamaSupervisor

if __name__ == "__main__":

    dev_mode = os.environ.get("LLHAMA_DEV_MODE") == "1"

    shared_logger.set_level(LogLevel.INFO)

    if dev_mode:        
        sys.stdout = shared_logger
        sys.stderr = shared_logger
        print("Running in dev mode")
    else:
        print("Running in production mode - stdout is muted")
        


    supervisor_instance = LocalLLHamaSupervisor()
    supervisor_instance.run_main_loop()