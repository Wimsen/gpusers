import subprocess
import pprint
import os
import time
import atexit
import pytz
import psutil
import requests
import pandas as pd
from pprint import pprint

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pymongo import MongoClient
from flask import Flask, render_template, g
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

client = MongoClient(os.environ["MONGO_URI"])
db = client["heroku_f19b61q3"]
statistics = {}

def get_users():
    global statistics
    gpu_usage = []

    nvidia_output = subprocess.check_output(['nvidia-smi']).decode('utf-8').split("\n")
    in_process_region = False
    processes = []

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
            memory = [word for word in line.split() if "MiB" in word]
            gpu_usage.append({
                "usage": usage,
                "memory": "{} / {}".format(memory[0], memory[1])
            })

        if not in_process_region:
            if "Processes" in line:
                in_process_region = True

        if in_process_region:
            numbers = [int(word) for word in line.split() if word.isdigit()]
            mem = [word for word in line.split() if "MiB" in word]
            if(len(numbers) >= 2):
                mem_mb = int(mem[0].replace("MiB", ""))
                mem_gb = "{:.3f} GB".format(mem_mb / 1000)
                processes.append({
                    "device": str(numbers[0]),
                    "pid": str(numbers[1]),
                    "mem": mem_gb
                    })

    for d in processes:
        p = psutil.Process(int(d["pid"]))
        d["process_name"] = " ".join(p.cmdline())
        d["user"] = p.username()

        created_datetime = datetime.fromtimestamp(p.create_time())
        now = datetime.now()
        diff = relativedelta(now, created_datetime)
        days = str(diff.days).zfill(2)
        hours = str(diff.hours).zfill(2)
        minutes = str(diff.minutes).zfill(2)
        d["runtime"] = "{}d {}h {}m".format(days, hours, minutes)

    statistics["gpu_usage"] = gpu_usage

    content = {
        "gpu_usage": gpu_usage,
        "processes": processes
    }
    res = requests.post('https://gpusers.herokuapp.com/post_users', json=content)
    print(res)


def save_usage():
    print("save usage ")
    tz = pytz.timezone('Europe/Oslo')
    now = datetime.now(tz=tz)

    for device, usage in enumerate(statistics["gpu_usage"]):

        user_id = db.usage.insert_one({
            'date': now,
            'device': device,
            'usage': int(usage["usage"].strip("%"))
         })

if __name__ == '__main__':
    get_users()
    save_usage()

    scheduler = BackgroundScheduler()
    scheduler.add_job(get_users, 'interval', seconds=20)
    scheduler.add_job(save_usage, 'interval', seconds=60)
    scheduler.start()
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        # Not strictly necessary if daemonic mode is enabled but should be done if possible
        scheduler.shutdown()
