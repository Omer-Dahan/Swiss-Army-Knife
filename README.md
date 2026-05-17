<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-green?style=for-the-badge&logo=python)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue?style=for-the-badge&logo=telegram)

**A multi-tool Telegram bot designed to provide a wide range of everyday utilities through an interactive interface and smart input detection.**

[🇺🇸 English](README.md)

</div>

---

| Feature | Description |
|---------|-------------|
| 🧠 **Smart Detection** | Auto-detects input (IPs, URLs, Plates, Numbers) and routes automatically |
| 🔗 **Short URLs** | Shorten any URL instantly using TinyURL |
| 📷 **QR Generator** | Convert text or links to QR code images |
| 📄 **PDF ↔ Image** | Convert JPG/PNG to PDF and extract first page of PDF to Image |
| 🌍 **IP Geolocation** | Track IP addresses to get Country, City, ISP, and Location |
| 💱 **Currency & VAT** | Live exchange rates and Israeli 18% VAT calculator |
| 🚗 **Vehicle Lookup** | Search Israeli license plates via open Gov APIs |
| 🔐 **Password Tools** | Generate secure passwords & check password strength |
| 🕯️ **Shabbat Times** | Get entry/exit times for Israeli cities |
| 🏦 **Bank Search** | Find Israeli bank branches and details |
| ⌨️ **Hebrew Fix** | Fix text accidentally typed in the wrong keyboard layout (Hebrew/English) |
| 🎲 **Dice Roller** | RPG-style dice rolling (D4, D6, D8, D10, D12, D20, D100) |
| 📓 **Personal Notes** | Save, edit, and manage private personal notes (per user) |
| 📲 **Direct WhatsApp** | Generate direct `wa.me` links from any phone number |
| 🕒 **World Clock** | Check current time in major global cities |

---

### 1️⃣ Clone the project
```bash
git clone https://github.com/Omer-Dahan/Swiss-Army-Knife.git
cd Swiss-Army-Knife
```

### 2️⃣ Create virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

### 4️⃣ Configuration
Create a `.env` file in the root directory and add your Telegram bot token:
```ini
BOT_TOKEN=your_bot_token_here
```

### 5️⃣ Run the bot
```bash
python bot.py
```

---

## 🎮 How to use

The bot offers a seamless Hebrew UI. You can interact with it in two main ways:

1. **Interactive Menu**: Send `/start` to open the main inline keyboard menu and click on the desired tool.
2. **Smart Input Detection**: Just send text to the bot! The smart dispatcher will automatically detect what you need:
   - Send an **IP address** `8.8.8.8` ➔ IP Geolocation
   - Send a **URL** `https://google.com` ➔ Offers URL Shortener or QR Code
   - Send an **Israeli License Plate** `1234567` ➔ Vehicle Lookup
   - Send a **Phone Number** `0501234567` ➔ Direct WhatsApp link
   - Send a **Number** `500` ➔ Offers VAT calculation or Currency conversion

---

## 🧱 Project Structure
```
Swiss Army Knife/
├── 📄 bot.py               # 🧠 Main bot entry point & dispatcher
├── 📄 .env                 # ⚙️ Configuration (Token)
├── 📄 requirements.txt     # 📦 Dependencies
├── 📂 data/                # 🗄️ Runtime storage for user notes (Auto-generated)
└── 📂 features/            # 🛠️ Individual feature modules
    ├── 📄 banks.py         # Bank branch search
    ├── 📄 currency.py      # Currency conversion
    ├── 📄 dice.py          # Dice roller
    ├── 📄 hebrew_fix.py    # Keyboard layout fixer
    ├── 📄 image_pdf.py     # PDF to Image and Image to PDF
    ├── 📄 location.py      # IP geolocation
    ├── 📄 notes.py         # Personal note management
    ├── 📄 password_gen.py  # Secure password generator
    ├── 📄 qrcode_gen.py    # QR code generator
    ├── 📄 shabbat.py       # Shabbat times
    ├── 📄 shorturl.py      # URL shortener
    ├── 📄 smart.py         # Smart text detection dispatcher
    ├── 📄 vat.py           # Israeli VAT calculator
    ├── 📄 vehicle.py       # Vehicle registry lookup
    ├── 📄 whatsapp.py      # WhatsApp links
    └── 📄 world_clock.py   # World clock
```

---

## ⚠️ Important Notes
> [!IMPORTANT]
> **API Limits**: Certain features like Geolocation and Currency Conversion rely on free public APIs. Excessive use might result in temporary rate limits.

> [!NOTE]
> **Data Privacy**: Personal notes are stored locally in the `data/` directory in JSON format per user. This data is not uploaded to the remote repository.

---

<div align="center">

**Made with ❤️ by Omer**

</div>
