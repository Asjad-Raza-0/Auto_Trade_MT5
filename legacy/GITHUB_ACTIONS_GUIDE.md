# 🚀 Complete Setup Guide: 24/7 Automated Alert Bot via GitHub Actions

This guide explains how to set up your **TG Capital Trading Alert Bot** to run **24/7 in the cloud completely FREE** using **GitHub Actions**, without requiring any VPS or credit card!

---

## How It Works

1. A automated workflow file (`.github/workflows/alert_bot.yml`) is stored in your repository.
2. Every 5 minutes (Monday through Friday), GitHub Actions automatically wakes up a virtual machine, runs a single market scan cycle (`python -m python_bot.main --once`), and instantly pushes Telegram alert notifications to your phone if a setup is confirmed.
3. It preserves your state machine (`bot_state.json`) between runs using GitHub Actions caching.

---

## Step 1: Push Your Codebase to GitHub

1. Create a **Private or Public Repository** on [GitHub](https://github.com/new).
2. Push your codebase to GitHub:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
   git branch -M main
   git push -u origin main
   ```

---

## Step 2: Set Up Your Telegram & API Secrets on GitHub

To securely store your API keys and Telegram credentials without committing them into your code:

1. Open your repository on GitHub.
2. Go to **Settings** -> **Secrets and variables** -> **Actions**.
3. Click **New repository secret** and add the following 3 secrets:

| Secret Name | Value Example | Description |
| :--- | :--- | :--- |
| `TWELVEDATA_API_KEY` | `your_twelvedata_api_key` | TwelveData API Key |
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdefGhI...` | Telegram Bot Token from `@BotFather` |
| `TELEGRAM_CHAT_ID` | `123456789` | Telegram Chat ID from `@userinfobot` |

*(Optional: Add `DISCORD_WEBHOOK_URL` if you want Discord alerts).*

---

## Step 3: Enable & Test the Workflow Manually

1. Click on the **Actions** tab at the top of your GitHub repository.
2. If prompted, click **"I understand my workflows, go ahead and enable them"**.
3. Select **"TG Capital Trading Alert Bot Scanner"** on the left menu.
4. Click **Run workflow** -> **Run workflow** (green button).

> 📱 **Verification**: GitHub will run your bot scan cycle immediately. If a trade setup is active, or if you click run during session hours (03:00 - 06:30 NY time), alerts will be pushed directly to your Telegram app!

---

## Step 4: Sit Back & Enjoy 24/7 Automated Scanning!

- Your bot will automatically scan markets every 5 minutes from Monday to Friday.
- You can check the execution history anytime under the **Actions** tab on GitHub.
- **Cost**: **$0.00 / Month** (100% Free forever!).
