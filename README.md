# Rails — Daily Financial Infrastructure Newsletter

Automated daily newsletter bot that scrapes financial infra news, generates a "Rails" issue via Claude, and saves it as a Google Calendar event at 09:00 KST.

## How it works

1. **Scrape** — Pulls news from CoinDesk, The Block, DL News, Cointelegraph (RSS) + Telegram channels
2. **Filter** — Keeps articles relevant to stablecoins, RWA, custody, settlement, Asia regulation, institutional adoption
3. **Generate** — Claude produces a full Rails issue following the format in `claude.md`
4. **Calendar** — Creates a 30-min event at 09:00 KST with the issue as description

Runs daily at 08:00 KST via GitHub Actions.

## Setup

### 1. GitHub Secrets

Add these secrets to your repo (`Settings → Secrets and variables → Actions`):

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GCP_SA_KEY` | Google Cloud service account JSON (entire JSON string) |
| `CALENDAR_ID` | Google Calendar ID (the `@group.calendar.google.com` address) |

### 2. Google Calendar service account

1. Create a GCP project and enable the **Google Calendar API**
2. Create a **service account** and download the JSON key
3. Share your target Google Calendar with the service account email (`xxx@xxx.iam.gserviceaccount.com`) — give it **"Make changes to events"** permission
4. Copy the entire JSON key content as the `GCP_SA_KEY` secret

### 3. Run manually

```bash
export ANTHROPIC_API_KEY=your_key
export GCP_SA_KEY='{"type":"service_account",...}'
export CALENDAR_ID=your_calendar_id@group.calendar.google.com
pip install -r requirements.txt
python main.py
```

## Food for Thought rotation (KST)

- **Monday** — Thesis Monday
- **Tuesday** — Counter-Take Tuesday
- **Wednesday** — Data Point Wednesday
- **Thursday** — Throwback Thursday
- **Friday** — Founder Friday
- **Saturday** — Long Read
- **Sunday** — Week in Review
