# ~/start-tmux-session.sh

SESSION_NAME="ssh-servers"

# Start a new tmux session
tmux new-session -d -s $SESSION_NAME

# Create windows and panes
tmux rename-window -t $SESSION_NAME:1 'Local'
tmux send-keys -t $SESSION_NAME:1 'zsh' C-m
tmux send-keys -t $SESSION_NAME:1 'htop' C-m


tmux new-window -t $SESSION_NAME:2 -n 's-01'
tmux send-keys -t $SESSION_NAME:2 'ssh admin@172.16.255.1' C-m
tmux send-keys -t $SESSION_NAME:2 'htop' C-m


tmux new-window -t $SESSION_NAME:3 -n 's-02'
tmux send-keys -t $SESSION_NAME:3 'ssh admin@172.16.255.12' C-m
tmux send-keys -t $SESSION_NAME:3 'htop' C-m


tmux new-window -t $SESSION_NAME:4 -n 's-03'
tmux send-keys -t $SESSION_NAME:4 'ssh admin@172.16.255.13' C-m
tmux send-keys -t $SESSION_NAME:4 'htop' C-m


tmux new-window -t $SESSION_NAME:5 -n 's-04'
tmux send-keys -t $SESSION_NAME:5 'ssh admin@172.16.255.14' C-m
tmux send-keys -t $SESSION_NAME:5 'htop' C-m


tmux new-window -t $SESSION_NAME:6 -n 'gc-07'
tmux send-keys -t $SESSION_NAME:6 'ssh admin@172.16.255.107' C-m
tmux send-keys -t $SESSION_NAME:6 'htop' C-m


tmux new-window -t $SESSION_NAME:7 -n 'gc-08'
tmux send-keys -t $SESSION_NAME:7 'ssh admin@172.16.255.108' C-m
tmux send-keys -t $SESSION_NAME:7 'htop' C-m


tmux new-window -t $SESSION_NAME:8 -n 'gc-09'
tmux send-keys -t $SESSION_NAME:8 'ssh admin@172.16.255.109' C-m
tmux send-keys -t $SESSION_NAME:8 'htop' C-m


# Attach to the session
tmux attach-session -t $SESSION_NAME