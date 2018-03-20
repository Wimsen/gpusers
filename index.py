import subprocess
import pprint
import os
import time
import atexit
import pytz
import psutil
import pandas as pd
from pprint import pprint

from datetime import datetime, timedelta
from flask_pymongo import PyMongo
from pymongo import MongoClient
from flask import Flask, render_template, g
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)
app.config["MONGO_URI"] = os.environ["MONGO_URI"]

mongo = PyMongo(app)
statistics = {}

@app.route("/")
def index():
    return render_template('index.html', statistics=statistics)


def get_and_calculate_usage_averages():
    global statistics
    with app.app_context():
        d0_hour_average = ["null" for i in range(24)]
        d0_lastday_hour_average = ["null" for i in range(24)]
        d0_weekday_average = ["null" for i in range(7)]

        d1_hour_average = ["null" for i in range(24)]
        d1_lastday_hour_average = ["null" for i in range(24)]
        d1_weekday_average = ["null" for i in range(7)]

        dev_0_items = list(mongo.db.usage.find({"device": 0}))
        dev_1_items = list(mongo.db.usage.find({"device": 1}))
        print(dev_0_items)


        # For some reason the hours get changed 1 back - move it forward again.
        # Also timedelta doesn't work with timezone datetimes. Remove it again.
        # TODO: This is not very good
        for item in dev_0_items:
            item['date'] = item['date'].replace(tzinfo=None)
            item['date'] = item['date'] + timedelta(hours=1)

        for item in dev_1_items:
            item['date'] = item['date'].replace(tzinfo=None)
            item['date'] = item['date'] + timedelta(hours=1)

        dev_0_lastday_items = [date for date in dev_0_items if date["date"] > (datetime.now() - timedelta(days=1))]
        dev_1_lastday_items = [date for date in dev_1_items if date["date"] > (datetime.now() - timedelta(days=1))]

        df0 = pd.DataFrame(dev_0_items)
        df1 = pd.DataFrame(dev_1_items)

        df0_lastday_hour_avg = {"usage": {}}
        df1_lastday_hour_avg = {"usage": {}}
        if len(dev_0_lastday_items) > 0 and len(dev_1_lastday_items) > 0:
            df0_lastday = pd.DataFrame(dev_0_lastday_items)
            df1_lastday = pd.DataFrame(dev_1_lastday_items)
            df0_lastday.index = pd.to_datetime(df0_lastday.date)
            df1_lastday.index = pd.to_datetime(df1_lastday.date)
            df0_lastday_hour_avg = df0_lastday.groupby(df0_lastday.index.hour).mean().round(2).to_dict()
            df1_lastday_hour_avg = df1_lastday.groupby(df1_lastday.index.hour).mean().round(2).to_dict()

        df0.index = pd.to_datetime(df0.date)
        df1.index = pd.to_datetime(df1.date)

        df0_weekday_avg = df0.groupby(df0.index.weekday).mean().round(2).to_dict()
        df0_hour_avg = df0.groupby(df0.index.hour).mean().round(2).to_dict()

        df1_weekday_avg = df1.groupby(df1.index.weekday).mean().round(2).to_dict()
        df1_hour_avg = df1.groupby(df1.index.hour).mean().round(2).to_dict()

        # TODO change loop
        for i in range(24):
            d0_hour_average[i] = df0_hour_avg["usage"][i] if i in dict.keys(
                df0_hour_avg["usage"]) else "null"
            d0_lastday_hour_average[i] = df0_lastday_hour_avg["usage"][i] if i in dict.keys(
                df0_lastday_hour_avg["usage"]) else "null"

            d1_hour_average[i] = df1_hour_avg["usage"][i] if i in dict.keys(
                df1_hour_avg["usage"]) else "null"
            d1_lastday_hour_average[i] = df1_lastday_hour_avg["usage"][i] if i in dict.keys(
                df1_lastday_hour_avg["usage"]) else "null"

        for i in range(7):
            d0_weekday_average[i] = df0_weekday_avg["usage"][i] if i in dict.keys(
                df0_weekday_avg["usage"]) else "null"
            d1_weekday_average[i] = df1_weekday_avg["usage"][i] if i in dict.keys(
                df1_weekday_avg["usage"]) else "null"

        statistics["d0_hour_average"] = d0_hour_average
        statistics["d0_lastday_hour_average"] = d0_lastday_hour_average
        statistics["d0_weekday_average"] = d0_weekday_average

        statistics["d1_hour_average"] = d1_hour_average
        statistics["d1_lastday_hour_average"] = d1_lastday_hour_average
        statistics["d1_weekday_average"] = d1_weekday_average


def get_users():
    global statistics
    with app.app_context():
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
            td = now - created_datetime
            hours, remainder = divmod(td.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            hours = str(hours).zfill(2)
            minutes = str(minutes).zfill(2)
            seconds = str(seconds).zfill(2)
            d["runtime"] = "{}h {}m {}s".format(hours, minutes, seconds)

        statistics["gpu_usage"] = gpu_usage
        statistics["processes"] = processes


def save_usage():
    with app.app_context():
        print("save usage ")
        tz = pytz.timezone('Europe/Oslo')
        now = datetime.now(tz=tz)

        for device, usage in enumerate(statistics["gpu_usage"]):
            user_id = mongo.db.usage.insert_one(
                {'date': now, "device": device, "usage": int(usage["usage"].strip("%"))})


if __name__ == '__main__':
    get_users()
    get_and_calculate_usage_averages()
    save_usage()

    executors = {
        'default': {'type': 'threadpool', 'max_workers': 20},
        'processpool': ProcessPoolExecutor(max_workers=5)
    }

    job_defaults = {
        'coalesce': False,
        'max_instances': 3
    }

    sched = BackgroundScheduler(
        executors=executors, job_defaults=job_defaults, timezone="EST", daemon=True)
    sched.start()
    sched.add_job(get_users, 'interval', seconds=20)
    sched.add_job(save_usage, 'interval', seconds=60)
    sched.add_job(get_and_calculate_usage_averages, 'interval', seconds=60 * 20)

    app.run(host="0.0.0.0", port=5000)
atexit.register(lambda: sched.shutdown(wait=False))
