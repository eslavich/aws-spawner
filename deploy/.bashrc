# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

export PS1="[\u@notebook \W]\$ "

export CRDS_PATH=~/crds_cache
export CRDS_SERVER_URL=https://jwst-crds.stsci.edu

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/opt/conda/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
        . "/opt/conda/etc/profile.d/conda.sh"
    else
        export PATH="/opt/conda/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<

conda activate notebook
