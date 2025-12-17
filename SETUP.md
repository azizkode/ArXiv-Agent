# Setup Guide

## Prerequisites

- Python 3.8 or higher
- OpenAI API key (or forwarded API key)
- Email account with SMTP access

## Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/arxiv-agent.git
cd arxiv-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and fill in your configuration:

```bash
nano .env  # or use vim, code, etc.
```

**Required Settings:**
- `OPENAI_API_KEY`: Your OpenAI API key
- `SMTP_SERVER`, `SMTP_PORT`: Your email provider's SMTP settings
- `SENDER_EMAIL`, `SENDER_PASSWORD`: Your email credentials
- `ARXIV_QUERY`: Your search keywords
- `RECIPIENT_EMAIL`: Where to send reports

### 4. (Optional) Set Up User Profile

For personalized recommendations:

```bash
cp user_profile.json.example user_profile.json
nano user_profile.json
```

Add your research interests and publications.

### 5. Test Email Configuration

Test your email settings:

```bash
python code/test_email.py
```

### 6. Run the Agent

```bash
python code/main.py
```

## Email Provider Setup

### Gmail

1. Enable 2-Step Verification
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the app password in `.env`

### QQ Mail

1. Enable SMTP in QQ Mail settings
2. Use authorization code (授权码) as password

### Other Providers

Check your email provider's SMTP documentation for:
- SMTP server address
- Port number (usually 587 for TLS, 465 for SSL)
- Authentication requirements

## Troubleshooting

### "Connection timeout"
- Check your SMTP server and port settings
- Verify firewall settings
- Try using SSL (port 465) instead of TLS (port 587)

### "Authentication failed"
- Verify your email and password
- For Gmail, use an App Password, not your regular password
- Check if 2FA is enabled and use appropriate credentials

### "API key invalid"
- Verify your OpenAI API key
- If using a forwarded key, ensure `OPENAI_BASE_URL` is set correctly

### "No papers found"
- Check your `ARXIV_QUERY` syntax
- Try simpler search terms
- Increase `ARXIV_DAYS` to look back further

## Next Steps

- Customize your search queries
- Add more publications to your profile
- Set up a cron job for daily reports
- Explore advanced features in the README

Happy researching! 🎉
