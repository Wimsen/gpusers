import subprocess
import pprint
import os
import time
import atexit

from flask import Flask, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


app = Flask(__name__)

massi_data = []
keith_data = []
other_data = []
gpu_usage = []


@app.route("/")
def index():
    return render_template('index.html', massi_data=massi_data, keith_data=keith_data, other_data=other_data, gpu_usage=gpu_usage)


def get_users():
    global massi_data, keith_data, other_data, gpu_usage

    nvidia_output = subprocess.check_output(['nvidia-smi']).decode('utf-8').split("\n")
    in_process_region = False
    data = []

    """
    Example of nvidia-smi output. We only want to process lines that are listed after
    the "processes" line, therefore the "in_process_region" check.

    +-----------------------------------------------------------------------------+
    | NVIDIA-SMI 384.90                 Driver Version: 384.90                    |
    |-------------------------------+----------------------+----------------------+
    | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
    | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
    |===============================+======================+======================|
    |   0  Tesla P100-PCIE...  Off  | 00000000:03:00.0 Off |                    0 |
    | N/A   73C    P0   164W / 250W |   4514MiB / 16276MiB |     94%      Default |
    +-------------------------------+----------------------+----------------------+
    |   1  Tesla P100-PCIE...  Off  | 00000000:82:00.0 Off |                    0 |
    | N/A   42C    P0    50W / 250W |   4666MiB / 16276MiB |     75%      Default |
    +-------------------------------+----------------------+----------------------+

    +-----------------------------------------------------------------------------+
    | Processes:                                                       GPU Memory |
    |  GPU       PID   Type   Process name                             Usage      |
    |=============================================================================|
    |    0    119559      C   python3                                     2333MiB |
    |    0    119676      C   python3                                     2171MiB |
    |    1    118261      C   python3                                     1253MiB |
    |    1    120084      C   python                                       815MiB |
    |    1    120583      C   python                                      1643MiB |
    |    1    121084      C   python3                                      945MiB |
    +-----------------------------------------------------------------------------+
    """
    for line in nvidia_output:
        if "%" in line and not in_process_region:
            usage = [word for word in line.split() if "%" in word][0]
            gpu_usage.append(usage)

        if not in_process_region:
            if "Processes" in line:
                in_process_region = True

        if in_process_region:
            numbers = [int(word) for word in line.split() if word.isdigit()]
            mem = [word for word in line.split() if "MiB" in word]
            if(len(numbers) >= 2):
                data.append({"device": str(numbers[0]), "pid": str(numbers[1]), "mem": str(mem[0])})

    ps_output = subprocess.check_output(['ps', 'aux']).decode('utf-8').split("\n")

    """
    Exmple of one line in ps_output
    root     142509  0.0  0.0      0     0 ?        S    Oct31   0:01 [kworker/39:2]
    """
    for d in data:
        for s in ps_output:
            if d["pid"] in s:
                d["user"] = s.split()[0]

                time_arr = s.split()[9].split(":")
                hours = 0
                minutes = 0
                seconds = 0
                if len(time_arr) == 3:
                    hours += int(time_arr[0])
                    hours += int(time_arr[1]) // 60

                    minutes += int(time_arr[1]) % 60
                    minutes += int(time_arr[2]) // 60

                    seconds += int(time_arr[2]) % 60
                elif len(time_arr) == 2:
                    hours += int(time_arr[0]) // 60

                    minutes += int(time_arr[0]) % 60
                    minutes += int(time_arr[1]) // 60

                    seconds += int(time_arr[1]) % 60

                # Add leading zeroes to make it sortable
                hours = str(hours).zfill(2)
                minutes = str(minutes).zfill(2)
                seconds = str(seconds).zfill(2)

                d["runtime"] = "{}h {}m {}s".format(hours, minutes, seconds)

    massi_users = ["andrehk", "ankalmar", "borgarrl", "jorgewil", "ruoccoma",
                   "bjorva", "eliezer", "erlenda", "havikbotn", "bjornhox", "krislerv"]
    keith_users = ["keith"]

    massi_data = [u for u in data if u["user"] in massi_users]
    keith_data = [u for u in data if u["user"] in keith_users]
    other_data = [u for u in data if u["user"]
                  not in keith_users and u["user"] not in massi_users]


if __name__ == '__main__':
    get_users()
    scheduler = BackgroundScheduler()
    scheduler.start()
    scheduler.add_job(
        func=get_users,
        trigger=IntervalTrigger(seconds=20),
        id='get_users',
        name='get users at interval ',
        replace_existing=True)
    app.run(host="0.0.0.0", port=5000)
# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())
