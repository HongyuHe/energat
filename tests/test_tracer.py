from energat.tracer import EnergyTracer


def test_tracer():
    tracer = EnergyTracer(1, attach=True, project="test")
    mapping = tracer.get_core_pkg_mapping()
    server_cputime = tracer.get_server_cputime()
    numa_mem = tracer.read_socket_numa_mem_mib("MemTotal")
    max_ranges = tracer.read_max_energy_ranges()

    num_sockets = len(set(mapping.values()))
    assert len(server_cputime) == num_sockets
    assert len(numa_mem) == num_sockets
    # * Currently only supports two domains.
    assert max_ranges.size == num_sockets * 2
