#!/usr/bin/env bash
set -x
set -e

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

    exit
}