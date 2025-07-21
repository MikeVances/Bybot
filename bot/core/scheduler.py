import time

class Scheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, interval):
        self.jobs.append((func, interval, time.time()))

    def run(self):
        while True:
            now = time.time()
            for i, (func, interval, last_run) in enumerate(self.jobs):
                if now - last_run >= interval:
                    func()
                    self.jobs[i] = (func, interval, now)
            time.sleep(1) 