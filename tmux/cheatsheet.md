## 🛠️ tmux CLI Cheatsheet

(ChatGPT)

### **Starting tmux**

- **Start a new session**
  ```bash
  tmux
  ```
- **Start a new session with a name**
  ```bash
  tmux new -s <session-name>
  ```

### **Session Management**

- **List all sessions**
  ```bash
  tmux ls
  ```
- **Attach to an existing session**
  ```bash
  tmux attach -t <session-name>
  ```
- **Detach from the current session**

  - Press `Ctrl + b`, then `d`

- **Kill a session by name**
  ```bash
  tmux kill-session -t <session-name>
  ```
- **Kill a session by ID**
  ```bash
  tmux kill-session -t <session-id>
  ```

### **Window Management**

- **Create a new window**
  ```bash
  tmux new-window
  ```
- **Rename the current window**
  ```bash
  tmux rename-window <new-name>
  ```
- **Move to the next window**
  ```bash
  tmux next-window
  ```
- **Move to the previous window**
  ```bash
  tmux previous-window
  ```
- **Kill the current window**
  ```bash
  tmux kill-window
  ```

### **Pane Management**

- **Split window horizontally**
  ```bash
  tmux split-window -h
  ```
- **Split window vertically**
  ```bash
  tmux split-window -v
  ```
- **Toggle between panes**
  ```bash
  tmux select-pane -U  # Up
  tmux select-pane -D  # Down
  tmux select-pane -L  # Left
  tmux select-pane -R  # Right
  ```
- **Kill the current pane**
  ```bash
  tmux kill-pane
  ```

### **Miscellaneous Commands**

- **List all key bindings**
  ```bash
  tmux list-keys
  ```
- **Reload tmux configuration**
  ```bash
  tmux source-file ~/.tmux.conf
  ```

---

## ⌨️ tmux Hotkey Cheatsheet

**Note:** The default tmux prefix key is `Ctrl + b`. All hotkeys start with this prefix unless you've changed it in your `~/.tmux.conf`.

### **Session Commands**

- **Detach from session**
  - `Ctrl + b` then `d`
- **Switch to another session**
  - `Ctrl + b` then `s`

### **Window Commands**

- **Create a new window**
  - `Ctrl + b` then `c`
- **Switch to next window**
  - `Ctrl + b` then `n`
- **Switch to previous window**
  - `Ctrl + b` then `p`
- **Select window by number**
  - `Ctrl + b` then `<number>`
- **Rename window**
  - `Ctrl + b` then `,`

### **Pane Commands**

- **Split window horizontally**
  - `Ctrl + b` then `"`
- **Split window vertically**
  - `Ctrl + b` then `%`
- **Switch panes**
  - `Ctrl + b` then arrow keys (`←`, `→`, `↑`, `↓`)
  - Alternatively: `Ctrl + b` then `o` to toggle
- **Resize pane**
  - `Ctrl + b` then `:` then type `resize-pane -D/U/L/R <number>`
- **Close pane**
  - `Ctrl + b` then `x` then `y` to confirm

### **Miscellaneous Hotkeys**

- **List all key bindings**
  - `Ctrl + b` then `?`
- **Reload configuration**
  - `Ctrl + b` then `:` then type `source-file ~/.tmux.conf` and press `Enter`

---

## 📋 Listing and Killing Sessions

### **List All tmux Sessions**

To view all active tmux sessions, use:

```bash
tmux ls
```

**Example Output:**

```
0: 2 windows (created Mon Apr 26 10:00:00 2023) [80x24]
1: 1 windows (created Mon Apr 26 10:05:00 2023) [80x24]
```

### **Kill a tmux Session by Name**

If you know the session name (e.g., `my_session`), run:

```bash
tmux kill-session -t my_session
```

### **Kill a tmux Session by ID**

Sessions are typically identified by their name or numerical ID (like `0`, `1`, etc.). To kill a session by ID:

```bash
tmux kill-session -t 0
```

**Note:** Replace `0` with the actual session ID you wish to terminate.

### **Kill All tmux Sessions**

To terminate all tmux sessions at once:

```bash
tmux kill-server
```

**⚠️ Caution:** This will close all tmux sessions and any running processes within them.

---

## 📚 Additional Resources

- **tmux Manual:** For an in-depth understanding, refer to the [tmux man page](https://man7.org/linux/man-pages/man1/tmux.1.html).
- **Online Tutorials:** There are numerous tutorials and guides available online that offer advanced usage tips and configurations.

---

With this cheatsheet, you should be well-equipped to handle most tmux tasks efficiently. Happy multiplexing!
