# UDP Buffer Size

- Added:
  boot.kernel.sysctl."net.core.rmem_max" = 7500000;
  boot.kernel.sysctl."net.core.wmem_max" = 7500000;

  to modules/nixos/system/boot/default.nix

# Mistakes were made

See Issue [#86](https://github.com/wg-lux/luxnix/issues/86)


### 🔧 What do `rmem_max` and `wmem_max` do again?

They define the **maximum** size (in bytes) that applications can request for **socket send (wmem)** and **receive (rmem)** buffers. These are especially relevant for:

- High-throughput UDP applications
- Real-time streaming or low-latency workloads
- Networking-heavy servers (e.g., video ingestion, game servers, etc.)

---

### 📏 Determining a Reasonable Buffer Size

Your system has **16 GB RAM**, and unless you’re pushing an edge case (like 10Gbit+ networking or ultra-low latency streaming), you likely don’t need huge buffers.

#### 💡 Default values on most Linux distros:

```bash
$ sysctl net.core.rmem_max
212992

$ sysctl net.core.wmem_max
212992
```

So, you're setting them to **~7.5 MB (7500000)** — a ~35x increase, which is quite aggressive and only needed if you're manually increasing socket buffer sizes in userland apps (e.g., with `setsockopt()`).

---

### ✅ Recommended safe max buffer size for your system:

| Use Case                    | Suggested Value                      |
| --------------------------- | ------------------------------------ |
| Normal desktop/server usage | **1 – 4 MB** (`1048576` – `4194304`) |
| Real-time audio/video (UDP) | **4 – 8 MB**                         |
| Custom high-performance app | **>8 MB** only if needed             |

So, for your setup, **a good starting point would be:**

```nix
boot.kernel.sysctl."net.core.rmem_max" = 4194304; # 4 MB
boot.kernel.sysctl."net.core.wmem_max" = 4194304;
```

If no apps are explicitly requesting large buffer sizes, even **2 MB (2097152)** is more than enough.

---

### 🧪 How to monitor actual usage

If you want to fine-tune based on actual use:

```bash
# See all socket buffer settings
ss -m | head -20

# Or for a running process using lots of sockets:
sudo lsof -nPi | grep UDP
```

And check `/proc/net/udp` or `/proc/net/sockstat` for system-wide socket stats.

---

### ⚠️ Notes

- These settings **do not** _reserve_ memory — they just define max allowed per socket.
- The more sockets you use, the higher potential memory pressure.
- If your apps aren't explicitly requesting large buffers, this setting won't do much — but can cause problems at boot or under load.
