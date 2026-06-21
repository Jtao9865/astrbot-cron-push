# AstrBot 定时推送插件 (CronPush)

## Functionality

- Uses AstrBot CronManager to register scheduled tasks (APScheduler backend)
- Uses MessageChain with At component to properly @ mention users
- Supports add, list, delete scheduled push tasks
- Supports immediate push and cross-session @ messages

## Installation

1. Copy the entire folder to AstrBot plugins directory:
   cp -r astrbot_plugin_cron_push_vscode ~/.astrbot/plugins/
2. Restart AstrBot
3. Enable the plugin in the management panel

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| /cron-add | Add scheduled push task | /cron-add 0 9 * * * 1000000 Morning! |
| /cron-list | List all tasks | /cron-list |
| /cron-del | Delete a task | /cron-del 1 |
| /cron-push | Immediate @ push | /cron-push 1000000 Hello |
| /cron-send | Send @ to any session | /cron-send group 123456 Hi everyone |

## Cron Expression Format

Standard 5-field: minute hour day month weekday

| Expression | Meaning |
|------------|---------|
| 0 9 * * * | Every day at 9:00 |
| 0 12 * * 1 | Every Monday at 12:00 |
| 0 */2 * * * | Every 2 hours |
| @daily | Daily midnight |
| @hourly | Hourly |

## File Structure

astrbot_plugin_cron_push_vscode/
  main.py              # Plugin main code
  metadata.yaml        # Plugin metadata
  requirements.txt     # Dependencies (none)
  README.md            # This file
