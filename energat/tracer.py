import datetime
import json
import multiprocessing
import os
import subprocess
import threading
import time
from functools import cache
from typing import *

import numpy as np
import numpy.typing as npt
import pandas as pd
import psutil

from energat.basepower import BaselinePower
from energat.common import *
from energat.target import TargetStatus

# * Load configurations.
# cfg = FLAGS.config


class EnergyTracer(object):
    def __init__(
        self, target_pid: int, attach=False, project: str = None, output: str = None
    ):
        if not target_exists(target_pid):
            logger.error(f"Target application ({target_pid}) doesn't exist!!!\n")
            exit(1)

        self.target_process = psutil.Process(target_pid) if target_pid > 0 else None
        self.core_pkg_map = self.get_core_pkg_mapping()
        self.num_cpu_sockets = len(set(self.core_pkg_map.values()))
        # * [[pkg_max1, pkg_max2, ...], [dram_max1, dram_max2, ...]]
        self.max_energy_ranges_j = self.read_max_energy_ranges()

        # ! Differentiate between processes and threads when tracing energy.
        self.target_processes: Set[int] = set()
        self.target_threads: Set[int] = set()

        self.tracer_process = multiprocessing.Process(
            name="EnergAt::tracer", target=self.run, args=[]
        )
        self.tracer_daemon_thread = None
        self.mutex = threading.Lock()
        self.iolock = threading.Lock()

        # * Target ID -> status.
        self.targets_status: Dict[int, "TargetStatus"] = {}
        # * Socket ID -> list of used mem mib.
        self.server_numa_mem_samples: Dict[int, List[float]] = {
            socket: [] for socket in range(self.num_cpu_sockets)
        }

        os.makedirs(FLAGS.output, exist_ok=True)

        self.traces: List[Dict[str, float]] = []
        project = project if project else str(round(time.time()))
        self.trace_file = (
            (FLAGS.output + f"/energat_traces_{project}.csv")
            if not output
            else output + ".csv"
        )

        self.baseline = BaselinePower(self.num_cpu_sockets)
        self.baseline_file = FLAGS.basefile

        if attach:
            self.load_baseline_power()
        return

    def run(self, rapl_interval_sec=FLAGS.interval):
        ts_start = time.perf_counter()
        if rapl_interval_sec < 0.05:
            logger.critical(
                f"RAPL sampling interval ({rapl_interval_sec}s) shouldn't be < 50ms"
            )

        self.tracer_daemon_thread = threading.Thread(
            name="tracer-daemon", target=self.sample_targets_status, daemon=True
        )
        self.tracer_daemon_thread.start()
        tasks = [self.tracer_process.pid, self.tracer_daemon_thread.native_id]
        logger.info(f"Tracer process PID: {self.tracer_process.pid}")
        logger.info(f"Daemon thread TID: {self.tracer_daemon_thread.native_id}")
        pin_tasks(tasks)

        # * [num_sockets x (pkg, dram)]
        # ! These temporary counters could overflow for long-running experiments
        # ! (but they aren't recorded in the traces).
        total_consumption = np.array(self.get_empty_energy_readings())
        baseline_consumption = np.array(self.get_empty_energy_readings())
        ascribable_consumption = np.array(self.get_empty_energy_readings())

        # * [num_sockets x 1]
        server_cputime_before = self.get_server_cputime()
        readings_before = self.read_pkg_mem_joules()
        ts_before = time.perf_counter()

        # * Obtain threads and processes before the start.
        self.update_targets()
        self.empty_targets_status()

        targets_alive = True

        with ProcessSignalHandler() as sighandler:
            while True:
                elapsed = time.perf_counter() - ts_before
                interval_delta_sec = rapl_interval_sec - elapsed
                if interval_delta_sec < 0:
                    logger.warn(
                        f"One lap exceeded RAPL interval by {-interval_delta_sec}s"
                    )
                else:
                    time.sleep(interval_delta_sec)

                """Reading energy from RAPL interface."""
                # * [2 x num_sockets]: Column i is the (cpu, dram) of socket i.
                readings_now = self.read_pkg_mem_joules()
                ts_now = time.perf_counter()
                total_energy_j = np.array(readings_now) - np.array(readings_before)
                if (total_energy_j < 0).any():
                    overflow_indices = np.where(total_energy_j < 0)
                    total_energy_j[overflow_indices] = +self.max_energy_ranges_j[
                        overflow_indices
                    ]
                    logger.warn(
                        f"Negative energy reading occurred -> Max RAPL ranges exceeded."
                    )

                total_consumption += total_energy_j
                duration_sec = ts_now - ts_before

                """Recording the cpu time of the targets for the duration of the energy readings."""
                self.record_targets_cputime()
                server_cputime_now = self.get_server_cputime()
                total_server_cputime_sec = np.array(server_cputime_now) - np.array(
                    server_cputime_before
                )

                """Subtracting static energy to get attributable energy."""
                pkg_percents, dram_percents = self.check_baseline_power()
                base_energy_j = self.compute_baseline_energy_joules(duration_sec)
                delta_energy_j = total_energy_j - base_energy_j

                if (delta_energy_j < 0).any():
                    delta_energy_j[delta_energy_j < 0] = 0
                    logger.warn(f"Total energy less than baseline energy!")

                baseline_consumption += base_energy_j

                """Ascribing energy from delta."""
                ascribed_energy_j, credit_fracs, tracer_energy_j = self.ascribe_energy(
                    delta_energy_j, total_server_cputime_sec
                )
                ascribable_consumption += ascribed_energy_j

                """Updating the targets and check if they are still alive."""
                targets_alive = self.update_targets()
                """Creating new status for all targets."""
                self.empty_targets_status()

                self.collect_results(
                    duration_sec,
                    total_energy_j,
                    base_energy_j,
                    ascribed_energy_j,
                    tracer_energy_j,
                    credit_fracs,
                    pkg_percents,
                    dram_percents,
                )

                if sighandler.stopped or not targets_alive:
                    self.collect_results(
                        duration_sec,
                        total_energy_j,
                        base_energy_j,
                        ascribed_energy_j,
                        tracer_energy_j,
                        credit_fracs,
                        pkg_percents,
                        dram_percents,
                        flash=True,
                    )

                    print()
                    logger.warn(f"Tracer was stopped!!!")
                    logger.info(
                        f"Total duration: {datetime.timedelta(seconds=time.perf_counter()-ts_start)}"
                    )
                    for socket in range(self.num_cpu_sockets):
                        logger.info(
                            f"Total energy of {socket=} (pkg, dram):"
                            f"\t {total_consumption[:, socket]} J"
                        )
                        logger.info(
                            f"Baseline energy of {socket=} (pkg, dram):"
                            f"\t {baseline_consumption[:, socket]} J"
                        )
                        logger.info(
                            f"Ascribed energy of {socket=} (pkg, dram):"
                            f"{ascribable_consumption[:, socket]} J"
                        )
                    return

                """Carrying results to the next iteration."""
                server_cputime_before, readings_before, ts_before = (
                    server_cputime_now,
                    readings_now,
                    ts_now,
                )

            # *> End of tracer process loop.

    def sample_targets_status(self, sample_interval_s=FLAGS.rapl_period):
        while True:
            try:
                socket_used_mem = self.read_socket_numa_mem_mib("MemUsed")

                # * Get lock, making sure the tracer thread doesn't delete everything at this point.
                self.mutex.acquire()

                # * Collect system-wide memory usages.
                for socket in range(self.num_cpu_sockets):
                    self.server_numa_mem_samples[socket].append(socket_used_mem[socket])

                disappeared_targets = []
                for status in self.targets_status.values():
                    exists = target_exists(status.target.pid)
                    if not exists:
                        # ? Can/should we preserve partial results?
                        logger.warn(
                            f"(daemon) Stopped tracing status of {status.target.pid}"
                        )
                        disappeared_targets.append(status.target.pid)
                        continue

                    """Accumulating target residence counters."""
                    try:
                        core = status.target.cpu_num()
                        socket = self.core_pkg_map[core]
                        count = status.cpu_socket_residence_counters.get(socket, 0)
                        status.cpu_socket_residence_counters[socket] = count + 1
                    except psutil.NoSuchProcess:
                        logger.warn(f"{status.target.pid} has gone, but {exists=}")
                        continue

                    """Accumulating target private memory per socket."""
                    private_mem = self.get_target_private_mem_mib(status.target.pid)
                    for _socket in range(self.num_cpu_sockets):
                        samples = status.numa_mem_samples.get(_socket, [])
                        samples.append(private_mem[_socket])  # * Add new samples.
                        status.numa_mem_samples[_socket] = samples  # * Put them back.

                # * Update targets in case of deletion.
                for pid in disappeared_targets:
                    if pid in self.target_processes:
                        self.target_processes.remove(pid)
                    if pid in self.target_threads:
                        self.target_threads.remove(pid)
                    del self.targets_status[pid]

            finally:
                # * Always release the lock s.t. the main tracer process terminates.
                self.mutex.release()

            time.sleep(sample_interval_s)
        # *> End of while loop.

    def ascribe_energy(
        self, total_energy_j: npt.ArrayLike, total_server_cputime_sec: npt.ArrayLike
    ):
        """Computes ascribable CPU pkg and DRAM energies.

        :param total_energy_j: {npt.ArrayLike} [[pkg1, pkg2, ...], [mem1, mem2, ...]]
        :param total_server_cputime_sec: {npt.ArrayLike} [socket1, socket2, ...]
        :return: Ascribable energies in Joules.
        """
        is_tracer = lambda _id: _id in [
            self.tracer_process.pid,
            self.tracer_daemon_thread.native_id,
        ]

        ascribable_energy_j = np.zeros_like(total_energy_j)
        tracer_energy_j = np.zeros_like(total_energy_j)
        if not self.targets_status:
            # * No active targets.
            return ascribable_energy_j

        # * Get lock since so that no new samples can be added.
        self.mutex.acquire()

        ascribable_cputime = [0.0] * self.num_cpu_sockets
        tracer_cpu = [0.0] * self.num_cpu_sockets
        # ! Assume that all targets have the same #samples since no new targets are added during sampling,
        # ! although some dead/inactive ones might be deleted by the daemon.
        num_mem_samples = len(
            next(iter(self.targets_status.values())).numa_mem_samples[0]
        )
        accumulated_private_mem_samples = {
            socket: np.array([0.0] * num_mem_samples)
            for socket in range(self.num_cpu_sockets)
        }
        tracer_mem_samples = {
            socket: np.array([0.0] * num_mem_samples)
            for socket in range(self.num_cpu_sockets)
        }

        ascribed_threads = set()

        for _, status in self.targets_status.items():
            if not target_exists(status.target.pid):
                continue

            """Ascribing CPU energy."""
            target_cputime = status.cputime_delta
            socket_residence_probs = status.compute_socket_residence_probs(
                self.num_cpu_sockets
            )
            # * Distribute cpu times to sockets given corresponding residence probabilities.
            for socket in range(self.num_cpu_sockets):
                cputime = target_cputime * socket_residence_probs[socket]
                # * Tracer runtime.
                if is_tracer(status.target.pid):
                    tracer_cpu[socket] += cputime
                else:
                    ascribable_cputime[socket] += cputime

            """Ascribing DRAM energy."""
            is_thread = False
            if status.target.pid in self.target_threads:
                is_thread = True
                if status.target.pid in ascribed_threads:
                    # * Dedupe: Threads share memory with other threads of the same process group.
                    continue

            for socket in range(self.num_cpu_sockets):
                # * Accumulate memory sample points across targets.
                if is_tracer(status.target.pid):
                    tracer_mem_samples[socket] += np.array(
                        status.numa_mem_samples[socket]
                    )
                else:
                    accumulated_private_mem_samples[socket] += np.array(
                        status.numa_mem_samples[socket]
                    )

            # * Dedupe.
            if is_thread:
                siblings = {t.id for t in status.target.threads()}
                ascribed_threads.update(siblings)

        # * Prevent numeric errors.
        SMALL_CONST = 1e-5
        credit_fracs = self.get_empty_energy_readings()
        ascribable_cputime = np.array(ascribable_cputime)
        for socket in range(self.num_cpu_sockets):
            # * [2 x num_sockets]: Column i is the (cpu, dram) of socket i.
            cpu_energy, dram_energy = total_energy_j[:, socket]

            """Crediting CPU package energy."""
            gamma_cpu = FLAGS.gamma
            cpu_credit_frac = (
                min(1.0, ascribable_cputime[socket] / total_server_cputime_sec[socket])
                if total_server_cputime_sec[socket] > 0
                else SMALL_CONST
            )
            ascribable_energy_j[0][socket] = cpu_energy * (cpu_credit_frac**gamma_cpu)
            credit_fracs[0][socket] = cpu_credit_frac

            """Crediting DRAM energy."""
            server_mem_samples = np.array(self.server_numa_mem_samples[socket])
            mem_indices_zeros = np.where(server_mem_samples == 0)
            # * Prevent numeric errors for Option 1 while keeping Option 2 vaiable.
            server_mem_samples[mem_indices_zeros] = SMALL_CONST
            accumulated_private_mem_samples[socket][mem_indices_zeros] = SMALL_CONST

            delta_mem = FLAGS.delta
            # ? Option 1: more robust to outliers but losing memory peaks.
            mem_credit_frac = min(
                1.0,
                (accumulated_private_mem_samples[socket] / server_mem_samples).mean(),
            )
            # ? Option 2: less robust to outliers.
            # mem_credit_frac = min(1., accumulated_private_mem_samples[socket].sum()/server_mem_samples.sum())

            ascribable_energy_j[1][socket] = dram_energy * (
                mem_credit_frac**delta_mem
            )
            credit_fracs[1][socket] = mem_credit_frac

            """Crediting tracer energy."""
            tracer_cpu_frac = min(
                1.0, tracer_cpu[socket] / total_server_cputime_sec[socket]
            )
            tracer_energy_j[0][socket] = cpu_energy * (tracer_cpu_frac**gamma_cpu)

            tracer_mem_frac = min(
                1.0, (tracer_mem_samples[socket] / server_mem_samples).mean()
            )
            # tracer_mem_frac = min(1., tracer_mem_samples[socket].sum()/server_mem_samples.sum())
            tracer_energy_j[1][socket] = dram_energy * (tracer_mem_frac**delta_mem)

            if round(time.time()) % FLAGS.logging == 0:
                logger.debug(
                    f"{socket=}: {cpu_credit_frac=: .3f}, {mem_credit_frac=: .3f}"
                )
                logger.debug(
                    f"{socket=}: {tracer_cpu_frac=: .3f}, {tracer_mem_frac=: .3f}"
                )

        self.mutex.release()
        return ascribable_energy_j, credit_fracs, tracer_energy_j

    def launch(self):
        if not self.baseline.estimated:
            logger.error(f"Baseline power hasn't been estimated")
        self.tracer_process.start()
        return

    def stop(self):
        self.tracer_process.terminate()
        # * (The daemon will stop at this point)
        return

    def __enter__(self):
        self.launch()
        return

    def __exit__(self, *args):
        # * Wait for the tracer process to start.
        time.sleep(FLAGS.interval)
        # * Stop the target process on exit.
        os.kill(self.tracer_process.pid, signal.SIGTERM)
        self.stop()
        return

    def estimate_baseline_power(self, save=False):
        logger.info("Estimating baseline power ...")
        interval_sec = FLAGS.rapl_period
        baseline_record = {}

        _ = psutil.cpu_percent(percpu=True)
        readings_before = self.read_pkg_mem_joules()

        time.sleep(interval_sec)

        readings_after = self.read_pkg_mem_joules()
        core_percents: List[float] = psutil.cpu_percent(percpu=True)

        total_energy_j = np.array(readings_after) - np.array(readings_before)

        for socket in range(self.num_cpu_sockets):
            pkg_energy_j, dram_energy_j = total_energy_j[:, socket]
            self.baseline.pkg_powers_watt[socket] = pkg_energy_j / interval_sec
            self.baseline.dram_powers_watt[socket] = dram_energy_j / interval_sec

        pkg_total_percents = np.zeros(self.num_cpu_sockets)
        for core, percent in enumerate(core_percents):
            socket = self.core_pkg_map[core]
            pkg_total_percents[socket] += percent
        else:
            self.baseline.pkg_percents = pkg_total_percents / (
                (core + 1) / self.num_cpu_sockets
            )  # * Core per package, assuming sockets have same # of cores.

        self.baseline.dram_percents = (
            np.array(self.read_socket_numa_mem_mib("MemUsed"))
            / np.array(self.read_socket_numa_mem_mib("MemTotal"))
            * 100
        )

        self.baseline.estimated = True

        logger.info(
            f"Estimated baseline power status over {interval_sec}s:\n"
            f"{self.baseline}"
        )

        if self.baseline.dram_percents.size == 0:
            logger.error(f"Empty baseline memory usages!")

        if save:
            baseline_record["pkg_base_w"] = list(self.baseline.pkg_powers_watt)
            baseline_record["dram_base_w"] = list(self.baseline.dram_powers_watt)
            baseline_record["pkg_base_percents"] = list(self.baseline.pkg_percents)
            baseline_record["dram_base_percents"] = list(self.baseline.dram_percents)
            with open(self.baseline_file, "w+") as f:
                json.dump(baseline_record, f)
                logger.info(f"Baseline power saved at {self.baseline_file}")
        return

    def check_baseline_power(self):
        """Checks if the server load is above that of the utilization
        when the baselines are estimated, and returns the current cpu/mem utilization.
        """
        core_percents: List[float] = psutil.cpu_percent(percpu=True)

        pkg_total_percents = np.zeros(self.num_cpu_sockets)
        for core, percent in enumerate(core_percents):
            socket = self.core_pkg_map[core]
            pkg_total_percents[socket] += percent
        else:
            pkg_percents = pkg_total_percents / (
                (core + 1) / self.num_cpu_sockets
            )  # * Core per package, assuming sockets have same # of cores.

        dram_percents = (
            np.array(self.read_socket_numa_mem_mib("MemUsed"))
            / np.array(self.read_socket_numa_mem_mib("MemTotal"))
            * 100
        )

        is_pkg_below_baseline = pkg_percents < self.baseline.pkg_percents
        if any(is_pkg_below_baseline):
            logger.warn(
                f"CPU usage of packages: {list(np.where(is_pkg_below_baseline))}\n"
                f"\t below baseline: {list(self.baseline.pkg_percents[is_pkg_below_baseline])}"
            )
            logger.warn("Subsequent energy measurements may not be as accurate")

        is_dram_below_baseline = dram_percents < self.baseline.dram_percents
        if any(is_pkg_below_baseline):
            logger.warn(
                f"DRAM usage of packages: {list(np.where(is_dram_below_baseline))}\n"
                f"\t below baseline: {list(self.baseline.dram_percents[is_dram_below_baseline])}"
            )
            logger.warn("Subsequent energy measurements may not be as accurate")

        return pkg_percents, dram_percents

    @cache
    def compute_baseline_energy_joules(self, duration_sec):
        """[ [pkg1_base, pkg2_base, ...], [dram1_base, dram2_base, ...]]"""
        # * Energy = Power x duration.
        return np.array(self.baseline.pkg_powers_watt * duration_sec), np.array(
            self.baseline.dram_powers_watt * duration_sec
        )

    def record_targets_cputime(self):
        assert self.targets_status, "Empty status (potential uninitialized)."

        # ! Get lock before modifing the shared status.
        self.mutex.acquire()

        disappeared_targets = []
        for pid, status in self.targets_status.items():
            success = status.record_cputime()
            if not success:
                logger.warn(f"(tracer proc) Stopped tracing status of {pid=}")
                disappeared_targets.append(pid)

        for pid in disappeared_targets:
            if pid in self.target_processes:
                self.target_processes.remove(pid)
            if pid in self.target_threads:
                self.target_threads.remove(pid)
            del self.targets_status[pid]

        self.mutex.release()
        return

    def empty_targets_status(self):
        targets = self.target_processes.copy()
        targets.update(self.target_threads)

        # * Get the lock before deleting everything s.t. the daemon is safe.
        self.mutex.acquire()
        self.targets_status = {
            pid: TargetStatus(pid) for pid in targets if target_exists(pid)
        }
        self.server_numa_mem_samples = {
            socket: [] for socket in range(self.num_cpu_sockets)
        }
        self.mutex.release()
        return

    def update_targets(self) -> True:
        """Updates monitored targets.

        :return: {bool} True if there are active targets.
        """
        inadmissible_status = ["terminated", psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE]
        processes = set()
        threads = set()

        if not target_exists(self.target_process.pid):
            logger.warn(
                f"Target application ({self.target_process.pid}) appears to have exited!!!"
            )
            return False
        elif self.target_process.status() in inadmissible_status:
            raise RuntimeError(
                f"Target application status: {self.target_process.status()}"
            )

        """Multithreaded main target."""
        if self.target_process.num_threads() > 1:
            logger.info(
                f"{self.target_process.pid=}: {self.target_process.num_threads()=}"
            )
            for thread in self.target_process.threads():
                # * NB: the main thread is included.
                threads.add(thread.id)
        else:
            processes.add(self.target_process.pid)

        for child_process in self.target_process.children(recursive=True):
            try:
                if child_process.status() in inadmissible_status:
                    logger.warn(f"{child_process.pid=}: {child_process.status()}")
                    continue

                if child_process.num_threads() > 1:
                    for thread in child_process.threads():
                        threads.add(thread.id)
                        if thread.id not in self.target_threads:
                            logger.info(
                                f"Added {thread.id=} to targets (from {child_process.pid}: #threads={child_process.num_threads()})"
                            )
                else:
                    processes.add(child_process.pid)
                    if child_process.pid not in self.target_processes:
                        logger.info(f"Added {child_process.pid=} to targets")
            except psutil.NoSuchProcess:
                logger.warn(f"{child_process.pid=} has gone")

        if not processes and not threads:
            logger.warn("No active targets found!")
            return False

        removed_processes = self.target_processes - processes
        removed_threads = self.target_threads - threads
        if removed_processes and removed_processes != {self.tracer_process.pid}:
            logger.info(f"Removed processes {removed_processes} from targets")
        if removed_threads and removed_threads != {self.tracer_daemon_thread.native_id}:
            logger.info(f"Removed processes {removed_threads} from targets")

        # * Update monitoring targets.
        self.target_processes, self.target_threads = processes, threads

        # * Always track the tracer process and daemon thread explicitly
        # * in case they are not children of the target (i.e., attach mode).
        self.target_processes.add(self.tracer_process.pid)
        self.target_threads.add(self.tracer_daemon_thread.native_id)
        return True

    def read_pkg_mem_joules(self) -> Tuple[List[float], List[float]]:
        """Reads intel RAPL sysfs interface.

        [2 x num_sockets] -- Column i is the (cpu, dram) of socket i.

        :return: {Tuple[List[float], List[float]]} Energy readings in joules
            ([pkg1, pkg2, ...], [mem1, mem2, ...])
        """
        rapl_dir = "/sys/class/powercap/intel-rapl/"
        pkg_readings, dram_readings = self.get_empty_energy_readings()
        for pkg in range(self.num_cpu_sockets):
            with open(f"{rapl_dir}/intel-rapl:{pkg}/name", "r") as f:
                pkg_domain = f.read()[:-1]
                assert pkg_domain == f"package-{pkg}", "Package domain mismatch"

            with open(f"{rapl_dir}/intel-rapl:{pkg}/energy_uj", "r") as f:
                pkg_ujoules = int(f.read()[:-1])
                pkg_readings[pkg] = pkg_ujoules / 1e6

            with open(
                f"{rapl_dir}/intel-rapl:{pkg}/intel-rapl:{pkg}:0/energy_uj", "r"
            ) as f:
                dram_ujoules = int(f.read()[:-1])
                dram_readings[pkg] = dram_ujoules / 1e6

        return pkg_readings, dram_readings

    def read_max_energy_ranges(self):
        rapl_dir = "/sys/class/powercap/intel-rapl/"
        pkg_ranges, dram_ranges = self.get_empty_energy_readings()
        for pkg in range(self.num_cpu_sockets):
            with open(f"{rapl_dir}/intel-rapl:{pkg}/name", "r") as f:
                pkg_domain = f.read()[:-1]
                assert pkg_domain == f"package-{pkg}", "Package domain mismatch"

            with open(f"{rapl_dir}/intel-rapl:{pkg}/max_energy_range_uj", "r") as f:
                pkg_ujoules = int(f.read()[:-1])
                pkg_ranges[pkg] = pkg_ujoules / 1e6

            with open(
                f"{rapl_dir}/intel-rapl:{pkg}/intel-rapl:{pkg}:0/max_energy_range_uj",
                "r",
            ) as f:
                dram_ujoules = int(f.read()[:-1])
                dram_ranges[pkg] = dram_ujoules / 1e6

        return np.array([pkg_ranges, dram_ranges])

    def load_baseline_power(self):
        if not os.path.isfile(self.baseline_file):
            logger.error(
                f"Baseline power record not found at {self.baseline_file}\n"
                f"Please first run: sudo energat -baseline"
            )
            os._exit(1)

        baseline_record = None
        with open(self.baseline_file, "r") as f:
            baseline_record = json.load(f)

        self.baseline.pkg_powers_watt = np.array(baseline_record["pkg_base_w"])
        self.baseline.dram_powers_watt = np.array(baseline_record["dram_base_w"])
        self.baseline.pkg_percents = np.array(baseline_record["pkg_base_percents"])
        self.baseline.dram_percents = np.array(baseline_record["dram_base_percents"])

        self.baseline.estimated = True
        return

    def collect_results(
        self,
        duration_sec: float,
        total_energy_joules: npt.ArrayLike,
        base_energy_joules: npt.ArrayLike,
        ascribed_energy_joules: npt.ArrayLike,
        tracer_energy_joules: npt.ArrayLike,
        credit_fracs: List[float],
        pkg_percents: List[float],
        dram_percents: List[float],
        flash=False,
    ):
        """Sinks results and periodically writes out.

        :param total_energy_consumption: [num_sockets x (pkg, dram)]
        :param ascribable_energy_consumption: [num_sockets x (pkg, dram)]
        """

        def flash_results():
            self.iolock.acquire()
            df = pd.DataFrame(self.traces)
            if os.path.isfile(self.trace_file):
                prevdf = pd.read_csv(self.trace_file)
                df = pd.concat([prevdf, df])
            df.to_csv(self.trace_file, index=False)
            # total_duration = df.duration_sec.sum()
            logger.info(f"Energy traces saved to {self.trace_file}")
            self.traces = []
            self.iolock.release()
            return

        ts = time.time()
        for socket in range(self.num_cpu_sockets):
            record = {
                "time": ts,
                "socket": socket,
                "duration_sec": duration_sec,
                "num_proc": len(self.target_processes),
                "num_threads": len(self.target_threads),
                "pkg_credit_frac": credit_fracs[0][socket],
                "dram_credit_frac": credit_fracs[1][socket],
                "total_pkg_joules": total_energy_joules[0][socket],
                "total_dram_joules": total_energy_joules[1][socket],
                "base_pkg_joules": base_energy_joules[0][socket],
                "base_dram_joules": base_energy_joules[1][socket],
                "ascribed_pkg_joules": ascribed_energy_joules[0][socket],
                "ascribed_dram_joules": ascribed_energy_joules[1][socket],
                "tracer_pkg_joules": tracer_energy_joules[0][socket],
                "tracer_dram_joules": tracer_energy_joules[1][socket],
                "pkg_percent": pkg_percents[socket],
                "dram_percent": dram_percents[socket],
            }
            self.traces.append(record)

        # total_duration = 0
        if flash or len(self.traces) >= 100:
            logger.info("Flash results")
            thread = threading.Thread(target=flash_results)
            thread.start()
        return

    def read_socket_numa_mem_mib(self, kind):
        """Reads NUMA memories of the specified `kind`.

        :param kind: One of ['MemUsed', 'MemTotal', 'MemFree'].
        :return: {List[float]} [num_sockets x 1]
        """
        # * This will be executed in a sub-shell but seems to be cheaper than pipe around
        # * between two threads, which yielded zombies sometimes.
        assert kind in ["MemUsed", "MemTotal", "MemFree"]
        output = subprocess.getoutput(f"numastat -m | grep {kind}").split()[1:-1]
        assert len(output) == self.num_cpu_sockets
        used_memories = list(map(float, output))
        return used_memories

    def get_target_private_mem_mib(self, pid):
        output = subprocess.getoutput(
            f"numastat -v -p {pid} | grep Private | tail -1"
        ).split()
        if "Private" not in output:
            logger.warn(f"Failed to get numa memory for {pid=}")
            return [0] * self.num_cpu_sockets

        output = output[output.index("Private") + 1 : -1]
        assert len(output) == self.num_cpu_sockets, f"{output=}"
        private_memories = list(map(float, output))
        return private_memories

    def get_server_cputime(self):
        """Get system-wide cpu time for each socket.

        :return: {List[float]} [num_sockets x 1]
        """
        cputime_per_socket = self.get_empty_energy_readings()[0]
        server_cputimes: List["CpuTimes"] = psutil.cpu_times(percpu=True)
        for core, cputimes in enumerate(server_cputimes):
            socket = self.core_pkg_map[core]
            cputime = cputimes.system + cputimes.user
            cputime_per_socket[socket] += cputime
        return cputime_per_socket

    def get_core_pkg_mapping(self) -> Dict[int, int]:
        core_pkg_map = {}
        core_count = psutil.cpu_count()
        for core in range(core_count):
            with open(
                f"/sys/devices/system/cpu/cpu{core}/topology/physical_package_id", "r"
            ) as f:
                pkg = int(f.read()[:-1])
                core_pkg_map[core] = pkg
        return core_pkg_map

    def get_empty_energy_readings(self):
        """[num_sockets x (pkg, mem)]"""
        return [0.0] * self.num_cpu_sockets, [0.0] * self.num_cpu_sockets
