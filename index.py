import subprocess
import pprint

import os

from flask import Flask, render_template

import time
import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


app = Flask(__name__)

massi_pids = []
keith_pids = []
other_pids = []
gpu_usage = []


@app.route("/")
def index():
    return render_template('index.html', massi_pids=massi_pids, keith_pids=keith_pids, other_pids=other_pids, gpu_usage=gpu_usage)


def get_users():
    global massi_pids, keith_pids, other_pids, gpu_usage

    gpu_usage = []

    test = subprocess.check_output(['nvidia-smi']).decode('utf-8').split("\n")
    active = False
    data = []
    for l in test:
        usages = [s for s in l.split() if "%" in s and len(s) > 0]
        if(len(usages) > 0):
            gpu_usage.append(usages[0])
        if not active:
            if "Processes" in l:
                active = True

        if active:
            ns = [int(s) for s in l.split() if s.isdigit()]
            mem = [s for s in l.split() if "MiB" in s]
            if(len(ns) == 2):
                # print(ns)
                # ns.append(mem[0])c

                data.append({"device": ns[0], "pid": ns[1], "mem": mem[0]})

    test = subprocess.check_output(['ps', 'aux']).decode('utf-8').split("\n")
    for d in data:
        for s in test:
            if "{}".format(d["pid"]) in s:
                d["user"] = s.split()[0]

    massi_users = ["andrehk", "ankalmar", "borgarrl", "jorgewil", "ruoccoma",
                   "bjorva", "eliezer", "erlenda", "havikbotn", "bjornhox", "krislerv"]
    keith_users = ["keith"]

    massi_pids = [u for u in data if u["user"] in massi_users]
    keith_pids = [u for u in data if u["user"] in keith_users]
    other_pids = [u for u in data if u["user"]
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
    app.run(host="0.0.0.0")
# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())
