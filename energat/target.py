from typing import *

import psutil

from energat.common import *


class TargetStatus(object):
    def __init__(self, pid):
        self.target: psutil.Process = psutil.Process(pid)
        self.last_cputime: float = read_cputime_sec(pid)

        self.cputime_delta: float = 0
        # TODO: Test single-socket scenario.
        # * Socket ID -> counter (empty in case of single socket).
        self.cpu_socket_residence_counters: Dict[int, int] = {}
        # * Socket ID -> list of sampled memories in mib (empty in case of single socket).
        self.numa_mem_samples: Dict[int, List[float]] = {}

    def record_cputime(self):
        if not target_exists(self.target.pid):
            return False

        curr_cputime = read_cputime_sec(self.target.pid)
        self.cputime_delta = curr_cputime - self.last_cputime
        self.last_cputime = curr_cputime

        assert self.cputime_delta >= 0, f"{self.target.pid=}: {self.cputime_delta=}"
        return True

    def compute_socket_residence_probs(self, num_sockets: int):
        if num_sockets < 2:
            # * For single-socket server.
            return [1.0]

        # ! Lock from the outside, otherwise deadlock.
        # # * Get lock to prevent the daemon from messing around.
        # mutex.acquire()

        probs = [0.0] * num_sockets
        total = sum(self.cpu_socket_residence_counters.values())
        # * The socket entry could be missing if a thread
        # * is never scheduled on any of its cores (though very unlikely).
        for socket in range(num_sockets):
            count = self.cpu_socket_residence_counters.get(socket, 0)
            # * Normalize to probabilities.
            probs[socket] = count / total

        # mutex.release()
        return probs
