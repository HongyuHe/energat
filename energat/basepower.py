import numpy as np


class BaselinePower(object):
    def __init__(self, num_cpu_sockets):
        self.estimated = False
        self.num_cpu_sockets = num_cpu_sockets
        self.pkg_powers_watt = np.zeros(num_cpu_sockets)
        self.dram_powers_watt = np.zeros(num_cpu_sockets)
        self.pkg_percents = np.zeros(num_cpu_sockets)
        self.dram_percents = np.zeros(num_cpu_sockets)

    def __repr__(self):
        return (
            f"\tPackage power [W]:       {self.pkg_powers_watt}\n"
            f"\tDRAM power [W]:          {self.dram_powers_watt}\n"
            f"\tPackage utilization [%]: {self.pkg_percents}\n"
            f"\tDRAM utilization [%]:    {self.dram_percents}\n"
        )
