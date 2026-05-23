# 🎬 Movie RSS Telegram Bot

RSS feed se automatically movie download links scrape karo aur Telegram channel mein bhejo.

## ⚙️ Flow

```
RSS Feed → Movie Page → openlinks.xyz (unlock) → Final Links → Telegram Channel
```

## 🚀 Quick Start (Docker)

### 1. Clone / Download karo
```bash
git clone <your-repo-url>
cd movie-rss-bot
```

### 2. .env file banao
```bash
cp .env.example .env
nano .env   # apni values bharo
```

### 3. Deploy karo
```bash
docker compose up -d
```

### 4. Logs dekho
```bash
docker compose logs -f
```

### 5. Stop karo
```bash
docker compose down
```

---

## 🔑 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | @BotFather se Telegram bot token |
| `CHANNEL_ID` | ✅ | — | Channel username ya numeric ID |
| `RSS_FEED_URL` | ❌ | uncutbaba.best/feed/ | RSS feed URL |
| `CHECK_INTERVAL` | ❌ | 300 | Seconds mein check interval |

---

## 🛠️ Manual Setup (Docker ke bina)

```bash
pip install -r requirements.txt

export BOT_TOKEN="your_token"
export CHANNEL_ID="@your_channel"

python bot.py
```

---

## 📁 Project Structure

```
movie-rss-bot/
├── bot.py              # Main bot code
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image build
├── docker-compose.yml  # Docker deploy config
├── .env.example        # Environment variables template
├── .env                # ⚠️ Apni values (git mein mat daalo!)
├── .gitignore
└── README.md
```

---

## ⚠️ Notes

- `data/` volume mein `seen_posts.json` store hota hai — container restart pe data safe rehta hai
- openlinks.xyz pe **image CAPTCHA** aayi toh bot manually bypass nahi kar sakta — us case mein 2captcha integrate karna hoga
