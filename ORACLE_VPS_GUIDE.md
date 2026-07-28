# Complete Setup Guide: Oracle Free VPS & MetaTrader 5 Demo Account

This step-by-step guide explains how to deploy your 24/7 Trading Alert Bot on an **Oracle Free Tier Linux VPS** and run the strategy on your **MetaTrader 5 Demo Account**.

---

## PART 1: 24/7 Alert Bot Deployment on Oracle Free VPS (Linux Ubuntu)

### Step 1: Create & Connect to Your Free Oracle VPS
1. Sign in to your [Oracle Cloud Console](https://cloud.oracle.com).
2. Click **Create a VM instance**.
3. Choose Image: **Canonical Ubuntu 22.04 LTS** (Always Free Eligible).
4. Download your SSH private key (`.key` or `.pem`).
5. Open your local terminal (or PowerShell) and connect to your VPS:
   ```bash
   ssh -i /path/to/your-key.key ubuntu@<YOUR_ORACLE_VPS_IP>
   ```

---

### Step 2: Install Python & Git on VPS
Once connected to your Oracle VPS, run:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip git -y
```

---

### Step 3: Clone Your Bot Repository
Upload or clone your project repository to your VPS home folder:
```bash
cd /home/ubuntu
git clone <YOUR_GIT_REPOSITORY_URL> tgcapital-bot
cd tgcapital-bot
```

---

### Step 4: Configure Your Telegram Credentials & API Keys
1. Create your `.env` file:
   ```bash
   nano .env
   ```
2. Paste your real API Key, Telegram Bot Token, and Chat ID:
   ```env
   TWELVEDATA_API_KEY=your_actual_twelvedata_api_key
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=123456789
   ```
   *(Press `Ctrl + O` then `Enter` to save, and `Ctrl + X` to exit).*

3. Install required Python packages:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

4. **Verify Telegram Connection**:
   ```bash
   python3 -m python_bot.main --test-alert
   ```
   *(Check your Telegram phone app — you should immediately receive a test signal message!).*

---

### Step 5: Run as 24/7 Background System Service (Auto-Start on Reboot)
To ensure your bot runs 24/7 even if you close your terminal or if Oracle restarts your VPS:

```bash
# 1. Copy the systemd service file
sudo cp tgcapital-bot.service /etc/systemd/system/

# 2. Reload and enable service
sudo systemctl daemon-reload
sudo systemctl enable tgcapital-bot

# 3. Start the bot
sudo systemctl start tgcapital-bot

# 4. Check status & live logs
sudo systemctl status tgcapital-bot
journalctl -u tgcapital-bot -f
```

---

## PART 2: Auto-Trading on MetaTrader 5 Demo Account

If you want MetaTrader 5 to **automatically place the Buy Limit orders** directly on your MT5 Demo Account when signals occur:

### Step 1: Copy EA Files to MetaTrader 5
1. Open MetaTrader 5 on your PC/Laptop.
2. Click **File -> Open Data Folder**.
3. Open `MQL5` folder.
4. Copy:
   - `mql5_ea/TGCapitalEA.mq5` into `MQL5/Experts/`
   - `mql5_ea/Include/` directory contents into `MQL5/Include/`

---

### Step 2: Enable WebRequest for Telegram (Optional in MT5)
1. In MT5, go to **Tools -> Options -> Expert Advisors**.
2. Check **Allow Algo Trading**.
3. Check **Allow WebRequest for listed URL** and add:
   `https://api.telegram.org`

---

### Step 3: Attach EA to Demo Account Chart
1. Open MetaEditor (press `F4` in MT5), open `TGCapitalEA.mq5` and press **Compile (F7)**. Ensure **0 errors and 0 warnings**.
2. Go back to MetaTrader 5, open a chart (e.g. `XAUUSD M30`).
3. Drag `TGCapitalEA` onto the chart.
4. Set inputs:
   - `InpRiskPercent`: `1.0` (1% risk per trade)
   - `InpSymbolsList`: `XAUUSD,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD,USDCHF,EURGBP`
   - `InpTelegramEnabled`: `true` (optional)
   - `InpTelegramBotToken`: `your_bot_token`
   - `InpTelegramChatID`: `your_chat_id`
5. Click **OK**. Enable **Algo Trading** button at the top toolbar of MT5.

---

### How the Workflow Operates
1. **Oracle VPS Alert Bot**: Runs 24/7 on Oracle Linux server scanning market data continuously. Whenever London Session setup triggers (03:00 - 06:30 NY), it pushes instant Telegram alert to your phone.
2. **MT5 Demo Account EA**: Scans MT5 market feeds on your demo account, automatically placing `BUY LIMIT` pending orders with exact 1% risk lot sizing and Candle B low stop loss.
