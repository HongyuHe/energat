#!/usr/bin/env bash
find . -depth -type d -execdir \
    sh -c 'touch "$PWD/$0" -r "$PWD/$0/$( ls -t "$PWD/$0" | head -n 1 )"' \
    {} \;
