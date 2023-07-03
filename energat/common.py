import logging
import os
import random
import signal
import subprocess
import sys
import time
from collections import namedtuple
from typing import *

import numpy as np
import psutil
from absl import flags
from ml_collections import config_flags

########### Command line options ###########
FLAGS = flags.FLAGS

flags.DEFINE_integer("pid", -1, "PID of the target application")
# flags.mark_flag_as_required('pid')

flags.DEFINE_string("name", None, "Name of the target application")
flags.DEFINE_boolean("check", False, "Check hardware support")
flags.DEFINE_boolean("basepower", False, "Estimate static power")

#
## * Configerations
#
flags.DEFINE_string("output", "./data/results", "Output directory")
flags.DEFINE_string(
    "basefile", "./data/baseline_power.json", "File recording the baseline power"
)
flags.DEFINE_float(
    "base_period", 2, "Sampling period in seconds for baseline power estimation"
)
flags.DEFINE_float(
    "rapl_period", 0.01, "Sampling period in seconds for RAPL power meters"
)
flags.DEFINE_float("interval", 1, "Interval in seconds between two power estimation")
flags.DEFINE_float("gamma", 0.3, "Non-linear scaling factor for CPU power")
flags.DEFINE_float("delta", 0.2, "Non-linear scaling factor for DRAM power")
flags.DEFINE_float(
    "logging", 2, "Logging interval in seconds (with `loglvl=debug` only)"
)
flags.DEFINE_enum("loglvl", "debug", ["info", "debug"], "Logging level (info/debug)")

config_flags.DEFINE_config_file("config", default="./configs/default.py")
FLAGS(sys.argv)
############################################

# * RNG for reproducibility.
rng = random.Random(42)

# * For typing.
CpuTimes = namedtuple(
    "CpuTimes", ["user", "system", "children_user", "children_system"]
)

"""Number of clock ticks per second."""
CLK_TCK_PER_SEC: int = os.sysconf(os.sysconf_names["SC_CLK_TCK"])


def read_cputime_sec(pid: float):
    """Get cpu time for a process/thread.

    (We can't use `psutil`, since it returns the aggregated values of a thread.)
    """
    if not target_exists(pid):
        logger.warn(f"{pid=} has gone")
        # ! Prevent div by 0
        return 0
    num_clock_ticks = 0
    # * We have to read the inner-most stat file to always get
    # * per-thread information (see: https://stackoverflow.com/a/59126812).
    # * (if it's a process, then it's its own runtime.)
    statf = f"/proc/{pid}/task/{pid}/stat"

    with open(statf, "r") as f:
        stat = (f.read()[:-1]).split()
        # * The 14th and 15th values are user and kernel times respectively.
        # * (https://man7.org/linux/man-pages/man5/proc.5.html)
        # print(f"{int(stat[14-1])=} {int(stat[15-1])=}")
        num_clock_ticks = int(stat[14 - 1]) + int(stat[15 - 1])
    # * Convert clock ticks to seconds.
    cputime_sec = num_clock_ticks / CLK_TCK_PER_SEC
    return cputime_sec


def target_exists(pid: int):
    statf = f"/proc/{pid}/task/{pid}/stat"
    return os.path.isfile(statf)


def pin_tasks(tasks: List[int], cores: List[int] = None, n_cores: int = 1):
    """Pins a list of tasks to the least-loaded cores.

    :param tasks: Tasks to pin.
    :param cores: List of cores to pin to.
    :param n_cores: Number of cores per task, defaults to 1
    """
    if not cores:
        # * Find the least-loaded cores.
        percents = psutil.cpu_percent(percpu=True)
        cores = np.argsort(percents)[:n_cores].tolist()
    for task in tasks:
        subprocess.run(
            ["sudo", "taskset", "-cp", ",".join(map(str, cores)), f"{task}"], check=True
        )

    logger.info(f"Pinned {tasks} to {cores=}")
    return


class ProcessSignalHandler(object):
    def __init__(self, signals=(signal.SIGINT, signal.SIGTERM)):
        self.signals = signals
        self.original_handlers = {}

    def __enter__(self):
        self.stopped = False
        self.released = False

        for sig in self.signals:
            self.original_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self.handler)

        return self

    def handler(self, signum, frame):
        self.release()
        self.stopped = True

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):
        if self.released:
            return False

        for sig in self.signals:
            signal.signal(sig, self.original_handlers[sig])

        self.released = True
        return True


def get_timestamp_ms():
    return round(time.time() * 1000)


class StdRapl(object):
    def __init__(self) -> None:
        pass

    def start(self):
        self.thread.start()

    def stop(self):
        thread = psutil.Process(self.thread.native_id)
        thread.send_signal(signal.SIGINT)

    def run_std_rapl(self):
        total_energy = float(
            subprocess.check_output(["sudo", "./uarch_rapl", "-t", "1000"]).decode()[
                :-1
            ]
        )
        print(f"StdRapl: {total_energy=}")


# * Create logger
logger = logging.getLogger("EnergAt")
if FLAGS.loglvl == "debug":
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
logger.propagate = False

# * Create console handler and set level to debug
ch = logging.StreamHandler()

# * Create formatter
formatter = logging.Formatter(
    "%(name)s @ %(asctime)s] %(levelname)-8s | %(message)s", "%b %d %H:%M:%S"
)

# * Add formatter to ch
ch.setFormatter(formatter)

# * Add ch to logger
logger.addHandler(ch)
