from ml_collections import config_dict


def get_config():
    default_config = config_dict.ConfigDict()

    default_config.OUTPUT_DIR = "./data/results"
    default_config.BASEPOWER_FILE = "./data/baseline_power.json"

    default_config.BASEPOWER_SAMPLING_SEC = 2
    default_config.ESTIMATION_INTERVAL_SEC = 1
    default_config.RAPL_SAMPLING_INTERVAL_SEC = 0.01

    default_config.GAMMA_CPU = 0.3
    default_config.DELTA_MEM = 0.2

    default_config.LOGGING_INTERVAL_SEC = 3

    return default_config
