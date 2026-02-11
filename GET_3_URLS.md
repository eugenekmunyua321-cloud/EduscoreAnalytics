# 🚀 GET YOUR 3 STREAMLIT URLS NOW!

## ⚡ INSTANT START (Copy and Paste This!)

```bash
./start_all.sh
```

**Then open your browser to these 3 URLs:**

```
✓ URL 1: http://localhost:5000  (Main App - Teachers/Staff)
✓ URL 2: http://localhost:5001  (Admin Dashboard)
✓ URL 3: http://localhost:5002  (Parents Portal)
```

## ✅ That's It! You Now Have 3 Streamlit URLs Running!

---

## 🪟 Alternative: Start Each URL Separately (Windows/Mac/Linux)

If `./start_all.sh` doesn't work, open **3 separate terminal windows** and run:

**Terminal 1 (URL 1):**
```bash
streamlit run app.py --server.port 5000
```
→ Opens: http://localhost:5000

**Terminal 2 (URL 2):**
```bash
streamlit run admin_features.py --server.port 5001
```
→ Opens: http://localhost:5001

**Terminal 3 (URL 3):**
```bash
streamlit run parents_portal_standalone.py --server.port 5002
```
→ Opens: http://localhost:5002

---

## 🛑 To Stop All 3 URLs

```bash
./stop_all.sh
```

Or press `Ctrl+C` in each terminal window.

---

## 📱 Access from Your Phone/Tablet (Same WiFi)

1. Find your computer's IP address:
   ```bash
   # Mac/Linux
   ifconfig | grep "inet " | grep -v 127.0.0.1
   
   # Windows
   ipconfig
   ```

2. Let's say your IP is `192.168.1.100`, use:
   ```
   http://192.168.1.100:5000  (Main App)
   http://192.168.1.100:5001  (Admin)
   http://192.168.1.100:5002  (Parents Portal)
   ```

---

## ❓ Troubleshooting

### "streamlit: command not found"

**Fix:**
```bash
pip install streamlit
pip install -r requirements.txt
```

### "Port already in use"

**Fix:**
```bash
./stop_all.sh
# Wait 5 seconds
./start_all.sh
```

### "Permission denied: ./start_all.sh"

**Fix:**
```bash
chmod +x start_all.sh
chmod +x stop_all.sh
./start_all.sh
```

---

## 🎯 What Each URL Is For

| URL | Port | Purpose | Who Uses It |
|-----|------|---------|-------------|
| URL 1 | 5000 | Main Application | Teachers, Staff |
| URL 2 | 5001 | Admin Dashboard | Administrators |
| URL 3 | 5002 | Parents Portal | Parents/Guardians |

---

## 🌐 For Production URLs (Your Own Domain)

Want URLs like:
- `app.yourschool.com`
- `admin.yourschool.com`
- `parents.yourschool.com`

Read: **HOW_TO_GET_URLS.md** or **DEPLOYMENT.md**

---

## 💡 Summary

**You asked for 3 Streamlit URLs. Here they are:**

1. `http://localhost:5000` ← Main App
2. `http://localhost:5001` ← Admin
3. `http://localhost:5002` ← Parents Portal

**To start them all:**
```bash
./start_all.sh
```

**Done!** 🎉

---

**Need more help?** Read the other guides:
- HOW_TO_GET_URLS.md (detailed guide)
- QUICK_START_URLS.txt (quick reference)
- URL_EXAMPLES.md (real examples)
