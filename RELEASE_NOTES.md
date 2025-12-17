# Release Notes

## Version 7.0 - Personalized Profile Edition

### 🎉 Major Features

- **Personalized Paper Discovery**: AI-generated search queries based on your research profile
- **Contextual Analysis**: Papers are analyzed against your publication history
- **Deep Source Inspection**: Automatic venue detection and GitHub link mining from LaTeX sources
- **Beautiful Email Reports**: Rich HTML formatting with badges and visualizations
- **Global Trend Analytics**: Visual charts showing paper distribution across research areas

### 📦 What's Included

- Core agent code (`code/main.py`)
- Test utilities (`code/test_email.py`, `code/test_source_scan.py`)
- Example usage (`code/example.py`)
- Configuration templates (`.env.example`, `user_profile.json.example`)
- Comprehensive documentation (README.md, SETUP.md, CONTRIBUTING.md)

### 🔒 Security

All sensitive information has been removed:
- No hardcoded email addresses
- No API keys or passwords
- No personal user profiles
- All credentials moved to environment variables

### 📚 Documentation

- **README.md**: Main documentation with features and quick start
- **SETUP.md**: Detailed setup instructions
- **CONTRIBUTING.md**: Guidelines for contributors
- **.env.example**: Configuration template
- **user_profile.json.example**: User profile template

### 🚀 Getting Started

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure
4. Optionally set up `user_profile.json` for personalized recommendations
5. Run: `python code/main.py`

### 📝 License

MIT License - See LICENSE file for details.

---

**Happy Researching!** 🎓
