from flask import Flask, Response
import time

app = Flask(__name__)

status = "Initializing..."
log_file_path = "/tmp/assistant_stdout.log"

# This function tails the log file and yields updates
def tail_log():
    with open(log_file_path, "r") as f:
        f.seek(0, 2)  # Go to the end of the file
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line

@app.route("/")
def index():
    return f"Assistant Status: {status}"

@app.route("/logs")
def logs():
    return Response(tail_log(), mimetype='text/plain')
