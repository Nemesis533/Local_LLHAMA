import os
import sys

# Add the ROOT directory (Local_LLHAMA) to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now the import will work
from local_llhama import main as run_main

def main():
    print("Starting Local Llahama in development mode...")  
    project_root = f"{os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))}/local_llhama"
    run_main(project_root)

if __name__ == "__main__":
    main()
