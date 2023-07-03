source /etc/profile

env2lmod
module load gcc/8.2.0
module load python/3.10.4
module load python_gpu
module load openblas
module load openmpi
module load cuda/11.7.0
# module load cudnn/8.2.4.15
module load cmake
module load eth_proxy
module load tmux
export TFDS_DATA_DIR="/cluster/scratch/honghe/tensorflow_datasets/"
export HF_DATASETS_CACHE="/cluster/scratch/honghe/huggingface_datasets/"