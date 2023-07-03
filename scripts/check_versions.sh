#!/bin/bash

python -c "import tensorflow as tf; print(tf.__version__)"
python -c "import torch;print(torch.cuda.nccl.version())"
nvcc --version

# ls -l /usr/lib/x86_64-linux-gnu/libcudnn.so.*  # * On colab only.
