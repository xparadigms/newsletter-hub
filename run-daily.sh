#!/bin/bash
# Japan Briefing — Daily runner
# Add to crontab: 0 8 * * * /Users/heechangkang/ai-test/newsletter/japan-newsletter/run-daily.sh

cd /Users/heechangkang/ai-test/newsletter/japan-newsletter
set -a
source .env.local
set +a
/Users/heechangkang/.pyenv/versions/3.9.19/bin/python main.py >> /tmp/japan-briefing.log 2>&1
