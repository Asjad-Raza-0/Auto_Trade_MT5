# Ubuntu VPS Storage Fix & Automated Log Rotation Guide

## Root Cause
When running the trading bot continuously on an Ubuntu VPS, two main factors consume disk storage over time:
1. **Unbounded Bot Log File (`bot_execution.log`)**: Previously used a basic file handler appending scan logs every 15 seconds without a size cap.
2. **Linux System Logs (`journald` / PM2 / nohup)**: Running Python background services captures standard output into VPS system logs or output files, which grow indefinitely without automatic retention limits.

---

## 1. Codebase Improvements Implemented

### Automatic Log Rotation (`RotatingFileHandler`)
- **Size Limit (`log_max_mb`)**: Capped at **10 MB** (default, configurable).
- **Backups (`log_backup_count`)**: Keeps up to **5** historical backup files (`bot_execution.log.1`, `bot_execution.log.2`, etc.).
- **Max Disk Consumption**: Total bot log footprint on disk will **never exceed ~50-60 MB** total.

### Configurable via `config.json`, `.env`, or CLI
- **`config.json`**:
  ```json
  "general": {
    "log_file": "bot_execution.log",
    "log_level": "INFO",
    "log_max_mb": 10,
    "log_backup_count": 5
  }
  ```
- **`.env`**:
  ```env
  LOG_MAX_MB=10
  LOG_BACKUP_COUNT=5
  ```
- **Command Line Overrides**:
  ```bash
  python python_bot/main.py --log-max-mb 10 --log-backup-count 5
  ```

### New Log Cleaning CLI Command (`--clean-logs`)
To instantly truncate active logs and delete old backup log files:
```bash
python python_bot/main.py --clean-logs
```

---

## 2. Immediate VPS Cleanup Commands (Run on Ubuntu VPS)

Run these commands in your Ubuntu VPS terminal to **free up storage immediately**:

### Step A: Truncate Trading Bot Logs
```bash
# Truncate the active log file without restarting the bot process
truncate -s 0 bot_execution.log

# Run the built-in clean command
python python_bot/main.py --clean-logs
```

### Step B: Clear Accumulated Ubuntu System Logs (`journald`)
If your bot runs as a `systemd` service or outputs to stdout, `journald` logs might be taking gigabytes.
```bash
# Check current system log size
sudo journalctl --disk-usage

# Vacuum journal logs down to 100MB
sudo journalctl --vacuum-size=100M
```

### Step C: Clear PM2 or Nohup Output Files (If applicable)
```bash
# If using PM2:
pm2 flush

# If using nohup (e.g. nohup python main.py > output.log 2>&1 &):
truncate -s 0 nohup.out
truncate -s 0 output.log
```

---

## 3. Permanent Ubuntu VPS Storage Optimization

### Limit Systemd Journal Size (`/etc/systemd/journald.conf`)
Prevent Linux system journal logs from ever growing past 100 MB:

1. Open journal configuration:
   ```bash
   sudo nano /etc/systemd/journald.conf
   ```
2. Set or uncomment:
   ```ini
   SystemMaxUse=100M
   ```
3. Save and restart journald:
   ```bash
   sudo systemctl restart systemd-journald
   ```
