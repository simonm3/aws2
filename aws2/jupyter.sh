export PYTHONPATH=/home/ubuntu/utils:$PYTHONPATH
tmux kill-session -t jupyter
tmux new -d -s jupyter jupyter notebook
