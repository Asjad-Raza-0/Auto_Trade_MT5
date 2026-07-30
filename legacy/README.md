# Legacy Artifacts (No Longer Used)

Everything in this folder belongs to the **previous** version of this project: the
*TG Capital London EMA Stack + FVG Trident v2.0* **alert-only** bot that ran on free
Linux cloud runners.

The project has since been converted into a **live MT5 auto-trading bot** running the
*1-Minute Structure Scalper* strategy (see [../CLAUDE.md](../CLAUDE.md)). None of these
files work with the new architecture, because the new bot talks to a **local
MetaTrader 5 terminal** through the `MetaTrader5` Python package, which requires a
Windows host with MT5 installed.

| File | Why it no longer applies |
| :--- | :--- |
| `alert_bot.yml` | GitHub Actions cloud runner — cannot reach your local MT5 terminal. |
| `GITHUB_ACTIONS_GUIDE.md` | Guide for the above workflow. |
| `ORACLE_VPS_GUIDE.md` | Oracle Cloud VPS is Linux; the `MetaTrader5` package is Windows-only. |
| `Dockerfile` / `docker-compose.yml` | Linux containers; same MT5 limitation. |
| `tgcapital-bot.service` | systemd unit (Linux only). See `../WINDOWS_DEPLOYMENT_GUIDE.md` instead. |
| `MQL5 Expert Advisor Development Prompt.pdf` | Spec for the removed MQL5 EA suite (`mql5_ea/`, deleted). |

**Safe to delete this whole folder.** It is kept only so nothing is lost — this repo has
no commits yet, so a delete would be unrecoverable.

For the current deployment path, read [../WINDOWS_DEPLOYMENT_GUIDE.md](../WINDOWS_DEPLOYMENT_GUIDE.md).
