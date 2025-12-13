import os

from .runtime_supervisor import LocalLLHamaSupervisor
from .shared_logger import LogLevel, shared_logger


def main():
    dev_mode = os.environ.setdefault("LLHAMA_DEV_MODE", "1") == "1"

    shared_logger.set_level(LogLevel.INFO)

    if dev_mode:
        import sys

        sys.stdout = shared_logger
        sys.stderr = shared_logger
        print("Running in dev mode")
    else:
        print("Running in production mode - stdout is muted")

    supervisor_instance = LocalLLHamaSupervisor()
    supervisor_instance.run_main_loop()


if __name__ == "__main__":
    main()
