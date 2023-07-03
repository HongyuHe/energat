#!/bin/bash

# Euler password file
PWD_FILE="../pwd.euler"

# GPU model
# GPU_TYPE="nvidia_a100_80gb_pcie"
GPU_TYPE="rtx_3090"

# Version
JNB_VERSION="1.3"

# Script directory
JNB_SCRIPTDIR=$(pwd)

# hostname of the cluster to connect to
JNB_HOSTNAME="euler.ethz.ch"

# order for initializing configuration options
# 1. Defaults values set inside this script
# 2. Command line options overwrite defaults
# 3. Config file options  overwrite command line options

# Configuration file default    : $HOME/.jnb_config
JNB_CONFIG_FILE="$HOME/.jnb_config"

# Username default              : no default
JNB_USERNAME=""

# Number of CPU cores default   : 1 CPU core
JNB_NUM_CPU=1

# Runtime limit default         : 1:00 hour
JNB_RUN_TIME="01:00"

# Memory default                : 1024 MB per core
JNB_MEM_PER_CPU_CORE=1024

# Number of GPUs default        : 0 GPUs
JNB_NUM_GPU=0

# Waiting interval default      : 60 seconds
JNB_WAITING_INTERVAL=60

# SSH key location default      : no default
JNB_SSH_KEY_PATH=""

# Software stack default        : new
JNB_SOFTWARE_STACK="new"

# Workdir default               : no default
JNB_WORKING_DIR=""

# Virtual env default           : no default
JNB_ENV=""

# jupyter lab default           : empty string (will start a notebook instead of lab)
JNB_JLAB=""

# julia kernels                 : FALSE -> no julia kernel; TRUE -> julia kernel
JNB_JKERNEL="FALSE"

# Extra cluster modules         : no additional modules (or override defaults for gcc, python, ...)
JNB_EXTRA_MODULES=()

# Use module collection         : no additional collection
JNB_MODULE_USE=""

# Set the remote python path    : Leave untouched
JNB_PYTHONPATH=""

# batch system to be used       : Options are LSF and SLURM
JNB_BATCH="SLURM"

###############################################################################
# Usage instructions                                                          #
###############################################################################

function display_help {
cat <<-EOF
$0: Script to start jupyter notebook/lab on Euler from a local computer

Usage: start_jupyter_nb.sh [options]

Required options:

        -u | --username       USERNAME         ETH username for SSH connection to Euler

Optional arguments:

        -b | --batch_sys      BATCHSYS         Batch system to use (LSF or SLURM)
        -c | --config         CONFIG_FILE      Configuration file for specifying options
        -g | --numgpu         NUM_GPU          Number of GPUs to be used on the cluster
        -h | --help                            Display help for this script and quit
        -i | --interval       INTERVAL         Time interval for checking if the job on the cluster already started
        -j | --julia          BOOL             Start jupyter notebook with (BOOL=TRUE) or without (BOOL=FALSE) julia kernel enabled
        -k | --key            SSH_KEY_PATH     Path to SSH key with non-standard name
        -l | --lab                             Start jupyter lab instead of a jupyter notebook
        -m | --memory         MEM_PER_CORE     Memory limit in MB per core
        -n | --numcores       NUM_CPU          Number of CPU cores to be used on the cluster
        -s | --softwarestack  SOFTWARE_STACK   Software stack to be used (old, new)
        -v | --version                         Display version of the script and exit
        -w | --workdir        WORKING_DIR      Working directory for the jupyter notebook/lab
             --extra-modules  EXTRA_MODULES    Load additional cluster modules before starting
             --module-use     MODULE_USE       Use additional cluster module collection before starting
             --pythonpath     PYTHONPATH       Set PYTHONPATH before starting
        -W | --runtime        RUN_TIME         Run time limit for jupyter notebook/lab in hours and minutes HH:MM

Examples:

        ./start_jupyter_nb.sh -u sfux -b SLURM -n 4 -W 04:00 -m 2048 -w /cluster/scratch/sfux

        ./start_jupyter_nb.sh -u sfux -b SLURM -n 1 -W 01:00 -m 1024 -j TRUE

        ./start_jupyter_nb.sh --username sfux --batch_sys SLURM --numcores 2 --runtime 01:30 --memory 2048 --softwarestack new

        ./start_jupyter_nb.sh -c $HOME/.jnb_config

Format of configuration file:

JNB_USERNAME=""             # ETH username for SSH connection to Euler
JNB_BATCH="SLURM"           # Choose SLURM or LSF as batch system
JNB_EXTRA_MODULES           # Additional modules to be loaded
JNB_NUM_CPU=1               # Number of CPU cores to be used on the cluster
JNB_NUM_GPU=0               # Number of GPUs to be used on the cluster
JNB_RUN_TIME="01:00"        # Run time limit for jupyter notebook/lab in hours and minutes HH:MM
JNB_MEM_PER_CPU_CORE=1024   # Memory limit in MB per core
JNB_WAITING_INTERVAL=60     # Time interval to check if the job on the cluster already started
JNB_SSH_KEY_PATH=""         # Path to SSH key with non-standard name
JNB_SOFTWARE_STACK="new"    # Software stack to be used (old, new)
JNB_WORKING_DIR=""          # Working directory for jupyter notebook/lab
JNB_ENV=""                  # Path to virtual environment
JNB_JLAB=""                 # "lab" -> start jupyter lab; "" -> start jupyter notebook
JNB_JKERNEL="FALSE"         # "FALSE" -> no Julia kernel; "TRUE" -> Julia kernel

EOF
exit 1
}

###############################################################################
# Parse configuration options                                                 #
###############################################################################

while [[ $# -gt 0 ]]
do
        case $1 in
                -h|--help)
                display_help
                ;;
                -v|--version)
                echo -e "start_jupyter_nb.sh version: $JNB_VERSION\n"
                exit
                ;;
                -u|--username)
                JNB_USERNAME=$2
                shift
                shift
                ;;
                -n|--numcores)
                JNB_NUM_CPU=$2
                shift
                shift
                ;;
                -W|--runtime)
                JNB_RUN_TIME=$2
                shift
                shift
                ;;
                -m|--memory)
                JNB_MEM_PER_CPU_CORE=$2
                shift
                shift
                ;;
                -c|--config)
                JNB_CONFIG_FILE=$2
                shift
                shift
                ;;
                -b |--batch_sys)
                JNB_BATCH=$2
                shift
                shift
                ;;
                -g|--numgpu)
                JNB_NUM_GPU=$2
                shift
                shift
                ;;
                -i|--interval)
                JNB_WAITING_INTERVAL=$2
                shift
                shift
                ;;
                -j|--julia)
                JNB_JKERNEL=$2
                shift
                shift
                ;;
                -k|--key)
                JNB_SSH_KEY_PATH=$2
                shift
                shift
                ;;
                -l|--lab)
                JNB_JLAB="lab"
                shift
                ;;
                -s|--softwarestack)
                JNB_SOFTWARE_STACK=$2
                shift
                shift
                ;;
                -w|--workdir)
                JNB_WORKING_DIR=$2
                shift
                shift
                ;;
                --extra-modules)
                JNB_EXTRA_MODULES=( $2 )
                shift
                shift
                ;;
                --module-use)
                JNB_MODULE_USE="$2"
                shift
                shift
                ;;
                --pythonpath)
                JNB_PYTHONPATH="$2"
                shift
                shift
                ;;
                *)
                echo -e "Warning: ignoring unknown option $1 \n"
                shift
                ;;
        esac
done

###############################################################################
# Check configuration options                                                 #
###############################################################################

# check if user has a configuration file and source it to initialize options
if [ -f "$JNB_CONFIG_FILE" ]; then
        echo -e "Found configuration file $JNB_CONFIG_FILE"
        echo -e "Initializing configuration from file ${JNB_CONFIG_FILE}:"
        cat "$JNB_CONFIG_FILE"
        source "$JNB_CONFIG_FILE"
fi

echo ''

# check that JNB_USERNAME is not an empty string when there is no entry in ~/.ssh/config
if [ -z "$JNB_USERNAME" ]; then
        if ! grep -q "^[Hh][Oo][Ss][Tt] \(.* \)\?euler.ethz.ch\( .*\)\?$" "$HOME/.ssh/config" ; then
            echo -e "Error: No ETH username is specified, terminating script\n"
            display_help
        fi
else
        echo -e "ETH username: $JNB_USERNAME"
fi

# check if JNB_JLAB is empty
if [ "$JNB_JLAB" == "lab" ]; then
        JNB_START_OPTION="lab"
        echo -e "Using jupyter lab instead of jupyter notebook"
else
        JNB_START_OPTION="notebook"
fi

# check which batch system to use
case $JNB_BATCH in
        LSF)
        echo -e "Using LSF batch system"
        ;;
        SLURM)
        echo -e "Using Slurm batch system"
        ;;
        *)
        echo -e "Error: Unknown batch system $JNB_BATCH_SYSTEM. Please either specify LSF or SLURM as batch system"
        display_help
        ;;
esac

# check number of CPU cores

# check if JNB_NUM_CPU an integer
if ! [[ "$JNB_NUM_CPU" =~ ^[0-9]+$ ]]; then
        echo -e "Error: $JNB_NUM_CPU -> Incorrect format. Please specify number of CPU cores as an integer and try again\n"
        display_help
fi

# check if JNB_NUM_CPU is <= 128
if [ "$JNB_NUM_CPU" -gt "128" ]; then
        echo -e "Error: $JNB_NUM_CPU -> Larger than 128. No distributed memory supported, therefore the number of CPU cores needs to be smaller or equal to 128\n"
        display_help
fi

if [ "$JNB_NUM_CPU" -gt "0" ]; then
        echo -e "Requesting $JNB_NUM_CPU CPU cores for running the jupyter $JNB_START_OPTION"
fi

# check number of GPUs

# check if JNB_NUM_GPU an integer
if ! [[ "$JNB_NUM_GPU" =~ ^[0-9]+$ ]]; then
        echo -e "Error: $JNB_NUM_GPU -> Incorrect format. Please specify the number of GPU as an integer and try again\n"
        display_help
fi

# check if JNB_NUM_GPU is <= 8
if [ "$JNB_NUM_GPU" -gt "8" ]; then
        echo -e "Error: No distributed memory supported, therefore number of GPUs needs to be smaller or equal to 8\n"
        display_help
fi

if [ "$JNB_NUM_GPU" -gt "0" ]; then
        echo -e "Requesting $JNB_NUM_GPU GPUs for running the jupyter $JNB_START_OPTION"
        if [ "$JNB_BATCH" == "LSF" ]; then
                JNB_SNUM_GPU="-R \"rusage[ngpus_excl_p=$JNB_NUM_GPU]\""
        else
                JNB_SNUM_GPU="--gpus=$GPU_TYPE:$JNB_NUM_GPU"
        fi
else
        JNB_SNUM_GPU=""
fi

if [ ! "$JNB_NUM_CPU" -gt "0" -a ! "$JNB_NUM_GPU" -gt "0" ]; then
        echo -e "Error: No CPU and no GPU resources requested, terminating script"
        display_help
fi

# check if JNB_RUN_TIME is provided in HH:MM format
if ! [[ "$JNB_RUN_TIME" =~ ^[0-9][0-9]:[0-9][0-9]$ ]]; then
        echo -e "Error: $JNB_RUN_TIME -> Incorrect format. Please specify runtime limit in the format HH:MM and try again\n"
        display_help
else
    echo -e "Run time limit set to $JNB_RUN_TIME"
fi

# check if JNB_MEM_PER_CPU_CORE is an integer
if ! [[ "$JNB_MEM_PER_CPU_CORE" =~ ^[0-9]+$ ]]; then
        echo -e "Error: $JNB_MEM_PER_CPU_CORE -> Memory limit must be an integer, please try again\n"
        display_help
else
    echo -e "Memory per core set to $JNB_MEM_PER_CPU_CORE MB"
fi

# check if JNB_WAITING_INTERVAL is an integer
if ! [[ "$JNB_WAITING_INTERVAL" =~ ^[0-9]+$ ]]; then
        echo -e "Error: $JNB_WAITING_INTERVAL -> Waiting time interval [seconds] must be an integer, please try again\n"
        display_help
else
    echo -e "Setting waiting time interval for checking the start of the job to $JNB_WAITING_INTERVAL seconds"
fi

# check if JNB_JKERNEL is TRUE or FALSE and if the new software stack is used (julia kernel not supported with the old software stack)
if [ "$JNB_JKERNEL" == "TRUE" ]; then
        JNB_JULIA="julia/1.6.5"
        if [ "$JNB_SOFTWARE_STACK" = "old" ]; then
                echo -e "Error: The Julia kernel is only supported when using the new software stack. Please change the software stack and try again\n"
                display_help
        fi
        echo -e "Enabling Julia kernel"
elif [ "$JNB_JKERNEL" == "FALSE" ]; then
        JNB_JULIA=""
else
        echo -e "Error: \$JNB_JKERNEL can only have the values TRUE or FALSE. Please specify a correct value for the -j/--julia parameter and try again\n"
        display_help
fi

# check which software stack to use
case $JNB_SOFTWARE_STACK in
        old)
        JNB_MODULE_COMMAND="new gcc/4.8.2 r/3.6.0 python/3.6.1 eth_proxy"
        JNB_MODULE_COMMAND+=" ${JNB_EXTRA_MODULES[@]}"
        echo -e "Using old software stack (new gcc/4.8.2 r/3.6.0 python/3.6.1 eth_proxy ${JNB_EXTRA_MODULES[@]})"
        ;;
        new)
        if [ "$JNB_NUM_GPU" -gt "0" ]; then
            JNB_MODULE_COMMAND="gcc/6.3.0 r/4.0.2 python_gpu/3.8.5 eth_proxy $JNB_JULIA"
            JNB_MODULE_COMMAND+=" ${JNB_EXTRA_MODULES[@]}"
            echo -e "Using new software stack (gcc/6.3.0 python_gpu/3.8.5 r/4.0.2 eth_proxy $JNB_JULIA ${JNB_EXTRA_MODULES[@]})"
        else
            JNB_MODULE_COMMAND="gcc/6.3.0 r/4.0.2 python/3.8.5 eth_proxy $JNB_JULIA"
            JNB_MODULE_COMMAND+=" ${JNB_EXTRA_MODULES[@]}"
            echo -e "Using new software stack (gcc/6.3.0 python/3.8.5 r/4.0.2 eth_proxy $JNB_JULIA ${JNB_EXTRA_MODULES[@]})"
        fi  
        ;;
        *)
        echo -e "Error: $JNB_SOFTWARE_STACK -> Unknown software stack. Software stack either needs to be set to 'new' or 'old'\n"
        display_help
        ;;
esac

# check if JNB_SSH_KEY_PATH is empty or contains a valid path
if [ -z "$JNB_SSH_KEY_PATH" ]; then
        JNB_SKPATH=""
else
        JNB_SKPATH="-i $JNB_SSH_KEY_PATH"
        echo -e "Using SSH key $JNB_SSH_KEY_PATH"
fi

# check if JNB_WORKING_DIR is empty
if [ -z "$JNB_WORKING_DIR" ]; then
        JNB_SWORK_DIR=""
else
        JNB_SWORK_DIR="--notebook-dir $JNB_WORKING_DIR"
        echo -e "Using $JNB_WORKING_DIR as working directory"
fi

# put together string for SSH options
if [ -z "$JNB_USERNAME" ]; then
    JNB_SSH_OPT="$JNB_SKPATH $JNB_HOSTNAME"
else
    JNB_SSH_OPT="$JNB_SKPATH $JNB_USERNAME@$JNB_HOSTNAME"
fi

###############################################################################
# Check for leftover files                                                    #
###############################################################################

# check if some old files are left from a previous session and delete them

# check for reconnect_info in the current directory on the local computer
echo -e "Checking for left over files from previous sessions"
if [ -f "$JNB_SCRIPTDIR/reconnect_info" ]; then
        echo -e "Found old reconnect_info file, deleting it ..."
        rm "$JNB_SCRIPTDIR/reconnect_info"
fi

# check for log files from a previous session in the home directory of the cluster
sshpass -f $PWD_FILE ssh -T $JNB_SSH_OPT <<ENDSSH
if [ -f "\$HOME/jnbinfo" ]; then
        echo -e "Found old jnbinfo file, deleting it ..."
        rm "\$HOME/jnbinfo"
fi
if [ -f "\$HOME/jnbip" ]; then
	echo -e "Found old jnbip file, deleting it ..."
        rm "\$HOME/jnbip"
fi 
ENDSSH

###############################################################################
# Start jupyter notebook/lab on the cluster                                   #
###############################################################################

# run the jupyter notebook/lab job on Euler and save ip, port and the token in the files jnbip and jninfo in the home directory of the user on Euler
echo -e "Connecting to $JNB_HOSTNAME to start jupyter $JNB_START_OPTION in a batch job"
# FIXME: save jobid in a variable, that the script can kill the batch job at the end

if [ "$JNB_BATCH" == "LSF" ]
then
sshpass -f $PWD_FILE ssh $JNB_SSH_OPT bsub -n $JNB_NUM_CPU -W $JNB_RUN_TIME -R "rusage[mem=$JNB_MEM_PER_CPU_CORE]" $JNB_SNUM_GPU  <<ENDBSUB
[ -n "$JNB_MODULE_USE" ] && module use "$JNB_MODULE_USE"
module load $JNB_MODULE_COMMAND
export XDG_RUNTIME_DIR=
JNB_IP_REMOTE="\$(hostname -i)"
echo "Remote IP:\$JNB_IP_REMOTE" >> \$HOME/jnbip
export JNB_RUN_TIME=$JNB_RUN_TIME
export JNB_START_TIME=`date +"%Y-%m-%dT%H:%M:%S%z"`
[ -n "$JNB_PYTHONPATH" ] && export PYTHONPATH="\$PYTHONPATH:$JNB_PYTHONPATH"
jupyter $JNB_START_OPTION --no-browser --ip "\$JNB_IP_REMOTE" $JNB_SWORK_DIR &> \$HOME/jnbinfo
ENDBSUB
elif [ "$JNB_BATCH" == "SLURM" ]
then
sshpass -f $PWD_FILE ssh $JNB_SSH_OPT "source /etc/profile && " sbatch -n $JNB_NUM_CPU --time=${JNB_RUN_TIME}:00 $JNB_SNUM_GPU <<ENDSBATCH
#!/bin/bash
[ -n "$JNB_MODULE_USE" ] && module use "$JNB_MODULE_USE"
module load $JNB_MODULE_COMMAND
export XDG_RUNTIME_DIR=
JNB_IP_REMOTE="\$(hostname -i)"
echo "Remote IP:\$JNB_IP_REMOTE" >> \$HOME/jnbip
export JNB_RUN_TIME=$JNB_RUN_TIME
export JNB_START_TIME=`date +"%Y-%m-%dT%H:%M:%S%z"`
[ -n "$JNB_PYTHONPATH" ] && export PYTHONPATH="\$PYTHONPATH:$JNB_PYTHONPATH"
[ -n "$JNB_ENV" ] && source $JNB_ENV/bin/activate
echo Using $(which jupyter-$JNB_START_OPTION)
jupyter $JNB_START_OPTION --no-browser --ip "\$JNB_IP_REMOTE" $JNB_SWORK_DIR --ContentsManager.allow_hidden=True &> \$HOME/jnbinfo
ENDSBATCH
fi

# wait until jupyter notebook/lab has started, poll every $JNB_WAITING_INTERVAL seconds to check if $HOME/jnbinfo exists
# once the file exists and is not empty, the notebook/lab has been startet and is listening
sshpass -f $PWD_FILE ssh $JNB_SSH_OPT <<ENDSSH
while ! [ -e \$HOME/jnbinfo -a -s \$HOME/jnbinfo ]; do
        echo 'Waiting for jupyter $JNB_START_OPTION to start, sleep for $JNB_WAITING_INTERVAL sec'
        sleep $JNB_WAITING_INTERVAL
done
ENDSSH

# get remote ip, port and token from files stored on Euler
echo -e "Receiving ip, port and token from jupyter $JNB_START_OPTION"
JNB_REMOTE_IP=$(sshpass -f $PWD_FILE ssh $JNB_SSH_OPT "cat \$HOME/jnbip | grep -m1 'Remote IP' | cut -d ':' -f 2")
JNB_REMOTE_PORT=$(sshpass -f $PWD_FILE ssh $JNB_SSH_OPT "cat \$HOME/jnbinfo | grep -m1 token | cut -d '/' -f 3 | cut -d ':' -f 2")
JNB_TOKEN=$(sshpass -f $PWD_FILE ssh $JNB_SSH_OPT "cat \$HOME/jnbinfo | grep -m1 token | cut -d '=' -f 2")

# check if the IP, the port and the token are defined
if  [[ "$JNB_REMOTE_IP" == "" ]]; then
cat <<EOF
Error: remote ip is not defined. Terminating script.
* Please check login to the cluster and check with bjobs if the batch job on the cluster is running and terminate it with bkill.
* Please check the /cluster/home/$JNB_USERNAME/jnbinfo on Euler for logs regarding the failure to identify the remote ip on the cluster
EOF
exit 1
fi

if  [[ "$JNB_REMOTE_PORT" == "" ]]; then
cat <<EOF
Error: remote port is not defined. Terminating script.
* Please check login to the cluster and check with bjobs if the batch job on the cluster is running and terminate it with bkill.
* Please check the /cluster/home/$JNB_USERNAME/jnbinfo on Euler for logs regarding the failure to identify the remote ip on the cluster
EOF
exit 1
fi

if  [[ "$JNB_TOKEN" == "" ]]; then
cat <<EOF
Error: token for the jupyter $JNB_START_OPTION session is not defined. Terminating script.
* Please check login to the cluster and check with bjobs if the batch job on the cluster is running and terminate it with bkill.
* Please check the /cluster/home/$JNB_USERNAME/jnbinfo on Euler for logs regarding the failure to identify the remote ip on the cluster
EOF
exit 1
fi

# print information about IP, port and token
echo -e "Remote IP address: $JNB_REMOTE_IP"
echo -e "Remote port: $JNB_REMOTE_PORT"
echo -e "Jupyter token: $JNB_TOKEN"

# get a free port on local computer
echo -e "Determining free port on local computer"
# JNB_LOCAL_PORT=$(python -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')
# FIXME: check if there is a solution that does not require python (as some Windows computers don't have a usable Python installed by default)
# if python is not available, one could use
JNB_LOCAL_PORT=$((3 * 2**14 + RANDOM % 2**14))
# as a replacement. No guarantee that the port is unused, but so far best non-Python solution

echo -e "Using local port: $JNB_LOCAL_PORT"

# put together URL
if [ "$JNB_START_OPTION" == "notebook" ]; then
        JNB_URL=http://localhost:$JNB_LOCAL_PORT/?token=$JNB_TOKEN
else
        JNB_URL=http://localhost:$JNB_LOCAL_PORT/lab?token=$JNB_TOKEN
fi

# write reconnect_info file
cat <<EOF > $JNB_SCRIPTDIR/reconnect_info
Restart file
Username          : $JNB_USERNAME
Remote IP address : $JNB_REMOTE_IP
Remote port       : $JNB_REMOTE_PORT
Local port        : $JNB_LOCAL_PORT
Jupyter token     : $JNB_TOKEN
SSH tunnel        : sshpass -f $PWD_FILE ssh $JNB_SSH_OPT -L $JNB_LOCAL_PORT:$JNB_REMOTE_IP:$JNB_REMOTE_PORT -N -T
URL               : http://localhost:$JNB_LOCAL_PORT/?token=$JNB_TOKEN

sshpass -f $PWD_FILE ssh $JNB_SSH_OPT -L $JNB_LOCAL_PORT:$JNB_REMOTE_IP:$JNB_REMOTE_PORT -N -T
EOF


sleep 3
# setup SSH tunnel from local computer to compute node via login node
# FIXME: check if the tunnel can be managed via this script (opening, closing) by using a control socket from SSH
echo -e "Setting up SSH tunnel for connecting the browser to the jupyter $JNB_START_OPTION"
sshpass -f $PWD_FILE ssh $JNB_SSH_OPT -L $JNB_LOCAL_PORT:$JNB_REMOTE_IP:$JNB_REMOTE_PORT -N -T 

# store pid of the SSH tunnel to terminate it after the session is over
JNB_SSH_TUNNEL_PID=$!

# SSH tunnel is started in the background, pause 5 seconds to make sure
# it is established before starting the browser
sleep 5

echo -e "Starting browser and connecting it to jupyter notebook"
echo -e "Connecting to url $JNB_URL"

# start local browser if possible
if [[ "$OSTYPE" == "linux-gnu" ]]; then
        xdg-open $JNB_URL
elif [[ "$OSTYPE" == "darwin"* ]]; then
        open $JNB_URL
elif [[ "$OSTYPE" == "msys" ]]; then # Git Bash on Windows 10
        start $JNB_URL
else
        echo -e "Your operating system does not allow to start the browser automatically."
        echo -e "Please open $JNB_URL in your browser."
fi
