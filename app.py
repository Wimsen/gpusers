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
from dateutil.relativedelta import relativedelta
from flask_pymongo import PyMongo
from pymongo import MongoClient
from flask import Flask, render_template, g, request
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)
app.config["MONGO_URI"] = os.environ["MONGO_URI"]

mongo = PyMongo(app)
statistics = {}

@app.route("/")
def index():
    return render_template('index.html', statistics=statistics)


@app.route('/post_users', methods=['POST'])
def post_users():
    print("received users")
    global statistics
    with app.app_context():
        content = request.get_json(silent=True)
        print(content)
        statistics["gpu_usage"] = content["gpu_usage"]
        statistics["processes"] = content["processes"]
    return "Success"


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


def save_usage():
    with app.app_context():
        print("save usage ")
        tz = pytz.timezone('Europe/Oslo')
        now = datetime.now(tz=tz)

        for device, usage in enumerate(statistics["gpu_usage"]):
            user_id = mongo.db.usage.insert_one(
                {'date': now, "device": device, "usage": int(usage["usage"].strip("%"))})


if __name__ == '__main__':
    get_and_calculate_usage_averages()

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
    sched.add_job(get_and_calculate_usage_averages, 'interval', seconds=60 * 20)

    app.run(host="0.0.0.0", port=5000)
