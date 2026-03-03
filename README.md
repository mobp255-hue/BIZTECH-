# BizTech – Business Technologies

BizTech is a full‑featured social marketplace platform connecting local businesses in Chivi District, Zimbabwe, with customers.  
It offers real‑time messaging, group chats, AI assistance, shopping cart with multiple payment methods (Flutterwave, Cash on Delivery, Wallet), WebRTC video calls, delivery tracking, multi‑language support (English, Shona, Ndebele), text‑to‑speech accessibility, integrated wallet, business verification badges, and local market weather/price widgets.

## ✨ Features

- **User Authentication** – Register/Login with profile images and E2EE key generation  
- **Business Listings** – Add, edit, delete listings with images, categories, location, phone  
- **Products** – Each listing can have multiple products with prices, availability, images  
- **Likes & Views** – Real‑time updates via Socket.IO  
- **Recommendations** – Users can recommend listings or products  
- **User Following** – Follow/unfollow other users, see followers/following  
- **Messaging** – Private 1‑to‑1 messages with unread indicators, E2EE optional  
- **Group Chats** – Create public/private groups, real‑time group messaging, typing indicators  
- **WebRTC Video Calls** – Peer‑to‑peer video calls with STUN (public)  
- **Shopping Cart** – Add/remove products, update quantities  
- **Payments** – Flutterwave, Cash on Delivery, Wallet  
- **Wallet** – Users have a wallet balance, can request withdrawals (admin processes)  
- **Verification Badges** – Users can apply for verification; admin approves  
- **Market Prices** – Admin can add/delete market prices displayed on homepage  
- **Weather Widget** – Live weather from Open‑Meteo (no API key)  
- **AI Chatbot** – Answers questions using built‑in knowledge or web search (DuckDuckGo)  
- **Multi‑language** – English, Shona, Ndebele (client‑side translations)  
- **Dark Mode** – Persistent theme toggle  
- **Text‑to‑Speech** – Listen to any text via browser speech synthesis  
- **Admin Panel** – Manage withdrawals, verification requests, market prices (user ID 1 only)  
- **Auto‑Database Repair** – Checks and rebuilds schema if missing tables/columns  
- **Rate Limiting** – Generous limits to prevent abuse  
- **Responsive Design** – Works on mobile and desktop with enhanced CSS animations, loading spinners, back‑to‑top button, fade‑in effects  

## 🛠 Technologies Used

- **Backend**: Python, Flask, Flask‑SocketIO, Flask‑SQLAlchemy, SQLite  
- **Real‑time**: Socket.IO (with Eventlet)  
- **Payments**: Flutterwave API (hardcoded keys – replace with your own)  
- **Cryptography**: cryptography library for E2EE key exchange  
- **Web Search**: BeautifulSoup + requests (scrapes DuckDuckGo HTML)  
- **Weather**: Open‑Meteo (free, no API key)  
- **Images**: Pillow for resizing uploaded images  
- **Frontend**: HTML5, CSS3, JavaScript, Leaflet (maps), Font Awesome, Google Fonts  

## 📋 Prerequisites

- Python 3.8 or higher  
- pip (Python package installer)  
- Git (optional)  

## 🚀 Installation

1. **Clone the repository** (or download the ZIP):
   ```bash
   git clone https://github.com/yourusername/biztech.git
   cd biztech
