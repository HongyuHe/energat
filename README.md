# EnergAt 🔋🎯

![version](https://img.shields.io/badge/version-1.0.6-blue) 
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://GitHub.com/hongyuhe/energat/graphs/commit-activity) 
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com) 
[![build](https://github.com/HongyuHe/energat/actions/workflows/test_basics.yaml/badge.svg)](https://github.com/HongyuHe/energat/actions/workflows/test_basics.yaml)
[![PyPI version](https://badge.fury.io/py/energat.svg)](https://badge.fury.io/py/energat)

EnergAt is a prototype implementation of the thread-level, NUMA-aware energy attribution model for multi-tenancy, as proposed in our [paper](https://hongyu.nl/papers/2023_hotcarbon_energat.pdf). It offers precise tracking of the energy consumption of your software application, even when it is running alongside other jobs from different users.

## Install 

To use EnergAt, the following requirements have to be met:

* Python 3.10
* Linux with root permission
* Intel RAPL with sysfs power capping interface
> **Note**
> There are several ways of accessing RAPL meters on Linux (e.g., via model-specific registers or perf), but the current implementation only supports the powercap interface. [Contributions](#contributing) are more than welcome!

Please run the following commands:
```bash
# * Configure the host system.
$ ./scripts/setup/init_system.sh
# * Use root permission for invoking energat with `sudo` later.
$ sudo python -m pip install energat
```

## Usage

> **Warning**
> Please always first estimate the static power of the machine by running the following command.
```python
$ sudo energat -basepower
```

### Python API

```python
import psutil, time
from energat.tracer import EnergyTracer

def xyz():
    tmp = 20_000
    for _ in range(100): 
        time.sleep(0.1)
        tmp = tmp * 0.314

with EnergyTracer(psutil.Process().pid, output='xyz_energy') as tracer:
    xyz()

# * The traces of `xyz()` will be saved to ./xyz_energy.csv at this point.
```

### Command line interface
First, check the system setup by running:
```bash
$ sudo energat -check

EnergAt @ Jul 03 10:30:27] INFO     | Socket count:        2
EnergAt @ Jul 03 10:30:27] INFO     | Host CPU times:      [334541.14, 334861.87]
EnergAt @ Jul 03 10:30:27] INFO     | Total NUMA memories: [32094.24, 32211.02]
EnergAt @ Jul 03 10:30:27] INFO     | RAPL domain ranges:  [262143.32885, 65712.999613]
EnergAt @ Jul 03 10:30:27] INFO     | System check passed!
```

Then, you can attach EnergAt to a running application for which you want to trace the energy consumption by providing its PID:
```bash
$ sudo energat -pid <PID>
```

Other command-line options include:
```console
$ sudo energat [FLAGS]

Commands:
  --pid PID                PID of the target application
                           (default: -1)
  --name NAME              Name of the target application
  --check                  Check hardware support
                           (default: False)
  --basepower              Estimate static power
                           (default: False)

Configurations:
  --output OUTPUT          Output directory
                           (default: ./data/results)
  --basefile BASEFILE      File recording the baseline power
                           (default: ./data/baseline_power.json)
  --base_period BASE_PERIOD
                           Sampling period in seconds for baseline power estimation
                           (default: 2)
  --rapl_period RAPL_PERIOD
                           Sampling period in seconds for RAPL power meters
                           (default: 0.01)
  --interval INTERVAL      Interval in seconds between two power estimations
                           (default: 1)
  --gamma GAMMA            Non-linear scaling factor for CPU power
                           (default: 0.3)
  --delta DELTA            Non-linear scaling factor for DRAM power
                           (default: 0.2)
  --logging LOGGING        Logging interval in seconds (with `loglvl=debug` only)
                           (default: 1)
  --loglvl LOGLVL          Logging level (info/debug)
                           (default: debug)
```

Once the target application finishes, EnergAt will save the energy traces to the `-output` directory and exits. You can also stop the tracing by <kbd>Ctrl+C</kbd>, and EnergAt will still save your result before exiting.

## Development 

EnergAt has been heavily tested on a few dual- and single-socket machines on CloudLab.

To set up the development environment, please run the following commands.
```bash
# * Run the setup script.
./scripts/setup/init_cloudlab.sh
# * Install python dependencies.
pip install -r requirements.txt
# * Configure git hooks.
pip install pre-commit
pre-commit install
pre-commit autoupdate
```

### Runtime Configuration

There are several ways by which you can change the configurations of EnergAt:
1. Directly change the default parameters in `configs/default.py`.
2. Provide your own config file in the `configs/` directory and specify it in the command line, e.g.,: 
```bash
$ sudo energat -config=./configs/your_config.py
```
3. Overwrite the default parameters through command-line flags, e.g.,:
```bash
$ sudo energat -config.OUTPUT_DIR='./out' -config.DELTA_MEM=0.1
```

### Contributing
Pull requests (PRs) are most welcome! Please follow the PR template: `.github/pull_request_template.md`.

## Citation
If you find this tool useful, please cite our paper:
```kt
@inproceedings{hotcarbon2023energat,
  author = {Hè, Hongyu and Friedman, Michal and Rekatsinas, Theodoros},
  title = {EnergAt: Fine-Grained Energy Attribution for Multi-Tenancy},
  booktitle = {2nd Workshop on Sustainable Computer Systems (HotCarbon '23)},
  year = {2023},
  month = {July},
  day = {9},
  location = {Boston, MA, USA},
  publisher = {ACM},
  address = {New York, NY, USA},
  pages = {8},
  doi = {10.1145/3604930.3605716},
  url = {https://doi.org/10.1145/3604930.3605716}
}

```


[travisci-badge]: https://travis-ci.com/HongyuHe/Tab2Know.svg?token=tLQAnpmJrz1TBJtLskoQ&branch=develop
[travisci-builds]: https://travis-ci.com/HongyuHe/Tab2Know
[maintain-badge]: https://img.shields.io/badge/Maintained%3F-yes-green.svg
[maintain-act]: https://github.com/HongyuHe/energat/graphs/commit-activity
[pr-badge]: https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square
[pr-act]: http://makeapullrequest.com
