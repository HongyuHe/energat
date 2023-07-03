#!/usr/bin/env bash
set -x

{
    sudo apt update -y && sudo apt upgrade -y

    sudo apt install numactl -y
    sudo apt install stress-ng -y

    # * Disable turbo boost
    ./scripts/turbo_boost.sh disable
    # * Just to make sure :)
    echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo

    # * Enable reading msr registers. 
    sudo modprobe msr
    # * Enable reading perf events.
    sudo sysctl -w kernel.perf_event_paranoid=-1
    # * The sysfs interface now requires root permission as of late 2020.
    # * See: https://github.com/mlco2/codecarbon/issues/244
    sudo chmod -R a+r /sys/class/powercap/intel-rapl

    # * Check available DVFS governors.
    cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
    # * Set all governors to performance.
    sudo bash -c 'for file in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo "performance" > $file; done'
    # * Verify the setting.
    cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

    # * Update python to 3.10
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt-get install python3.10 -y
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1 
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2 # * Larger number, higher priority/
    sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.10 2

    # * Install pip with the right version.
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
    sudo cp /users/"$USER"/.local/bin/pip /usr/bin/
    sudo apt install python3.10-distutils -y


    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    sudo apt install htop -y
    sudo apt-get install cpufrequtils -y
    sudo apt-get install linux-tools-common linux-tools-generic linux-tools-"$(uname -r)" -y
    sudo apt install numactl -y
    sudo apt-get install moreutils -y
    git config --global credential.helper store

    exit 0
}