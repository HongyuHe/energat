import sys

from energat.common import FLAGS, logger
from energat.tracer import EnergyTracer


def main():
    pid = 1  # * Use init process as a placeholder.
    if FLAGS.check:
        try:
            tracer = EnergyTracer(pid, attach=True, project="")
            logger.info(
                f"Socket count:        {len(set(tracer.get_core_pkg_mapping().values()))}"
            )
            logger.info(f"Host CPU times:      {tracer.get_server_cputime()}")
            logger.info(
                f"Total NUMA memories: {tracer.read_socket_numa_mem_mib('MemTotal')}"
            )
            logger.info(
                f"RAPL domain ranges:  {[r[0] for r in tracer.read_max_energy_ranges()]}"
            )
        except:
            logger.error("System check failed!")
            return 1
        logger.info("System check passed!")
        return 0

    if FLAGS.basefile:
        EnergyTracer(pid).estimate_baseline_power(save=True)
        return 0

    name = FLAGS.name if FLAGS.name else f"target-{FLAGS.pid}"
    if FLAGS.pid > 0:
        tracer = EnergyTracer(FLAGS.pid, attach=True, project=name)
        try:
            tracer.launch()
        except KeyboardInterrupt:
            tracer.stop()
    else:
        logger.error("No target process specified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
