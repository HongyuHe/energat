#!/usr/bin/env bash

PID=$1
numastat -v -p $PID | grep Total | tail -1
