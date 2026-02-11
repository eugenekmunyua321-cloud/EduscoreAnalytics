# How to Get 3 Different URLs for Each Entry Point

This guide explains exactly how to access your three EdusCore Analytics applications through different URLs.

## 🎯 Quick Answer

You have **TWO options** depending on where you want to run the applications:

### Option 1: Development/Testing (Localhost URLs)
✅ **Easiest and fastest** - No domain or server needed!

```
Main App:       http://localhost:5000
Admin:          http://localhost:5001
Parents Portal: http://localhost:5002
```

### Option 2: Production (Custom Domain URLs)
For real-world deployment with your own domain:

```
Main App:       http://app.yourschool.com
Admin:          http://admin.yourschool.com
Parents Portal: http://parents.yourschool.com
```

---

## 🚀 OPTION 1: Development/Testing URLs (Recommended to Start)

### What You Need
- Your computer (Windows, Mac, or Linux)
- Python installed
- This repository cloned

### Step-by-Step Instructions

#### Step 1: Install Dependencies
```bash
# Navigate to the project directory
cd EduscoreAnalytics

# Install Python dependencies
pip install streamlit pandas
pip install -r requirements.txt
```

#### Step 2: Start All Three Applications
```bash
# Make the script executable (Linux/Mac)
chmod +x start_all.sh

# Run the startup script
./start_all.sh
```

**On Windows:**
```bash
# Start each application in separate terminal windows

# Terminal 1 - Main App
streamlit run app.py --server.port 5000

# Terminal 2 - Admin Features
streamlit run admin_features.py --server.port 5001

# Terminal 3 - Parents Portal
streamlit run parents_portal_standalone.py --server.port 5002
```

#### Step 3: Access Your Applications

Open your web browser and visit:

| Application | URL | Who Uses It |
|------------|-----|-------------|
| **Main App** | http://localhost:5000 | Teachers, Staff |
| **Admin Dashboard** | http://localhost:5001 | Administrators |
| **Parents Portal** | http://localhost:5002 | Parents/Guardians |

**Screenshot: What You'll See**

```
Terminal Output:
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:5000
  Network URL: http://192.168.1.100:5000
```

#### Step 4: Share on Your Local Network (Optional)

If you want others on your WiFi to access the apps:

1. Find your computer's IP address:
   ```bash
   # Linux/Mac
   ifconfig | grep "inet "
   
   # Windows
   ipconfig
   ```

2. Share these URLs (replace `192.168.1.100` with your IP):
   ```
   Main App:       http://192.168.1.100:5000
   Admin:          http://192.168.1.100:5001
   Parents Portal: http://192.168.1.100:5002
   ```

#### Step 5: Stop All Applications
```bash
./stop_all.sh
```

Or press `Ctrl+C` in each terminal window.

---

## 🌐 OPTION 2: Production URLs (Your Own Domain)

### What You Need
- A domain name (e.g., `yourschool.com`, `myschool.edu`)
- A server or VPS (Ubuntu recommended)
- Basic Linux knowledge

### Overview of Steps

```
1. Buy/Have Domain → 2. Setup Server → 3. Configure DNS → 4. Install Apps → 5. Get URLs!
```

### Detailed Instructions

#### STEP 1: Get a Domain Name

**Purchase a domain from:**
- Namecheap (https://namecheap.com) - ~$10/year
- GoDaddy (https://godaddy.com) - ~$12/year
- Google Domains (https://domains.google) - ~$12/year

**Example:** Let's say you bought `brilliantschool.com`

#### STEP 2: Get a Server

**Option A: Cloud Server** (Recommended)
- DigitalOcean: $6/month (https://digitalocean.com)
- Linode: $5/month (https://linode.com)
- AWS Lightsail: $5/month (https://aws.amazon.com/lightsail)

**Option B: Use Your Own Computer as Server**
- Must be always on and connected to internet
- Need static IP or dynamic DNS

#### STEP 3: Configure DNS Records

This is the **KEY STEP** to get your 3 URLs!

Login to your domain registrar (where you bought the domain) and add these DNS records:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | app | YOUR_SERVER_IP | 300 |
| A | admin | YOUR_SERVER_IP | 300 |
| A | parents | YOUR_SERVER_IP | 300 |

**Real Example:**
If your server IP is `203.0.113.45` and domain is `brilliantschool.com`:

| Type | Name | Value | Result URL |
|------|------|-------|------------|
| A | app | 203.0.113.45 | app.brilliantschool.com |
| A | admin | 203.0.113.45 | admin.brilliantschool.com |
| A | parents | 203.0.113.45 | parents.brilliantschool.com |

**Screenshot Example (Namecheap DNS):**
```
Host    Type    Value               TTL
app     A       203.0.113.45        300
admin   A       203.0.113.45        300
parents A       203.0.113.45        300
```

**Wait Time:** DNS changes take 5-30 minutes to propagate worldwide.

#### STEP 4: Install and Configure on Server

```bash
# 1. Clone repository on server
git clone https://github.com/eugenekmunyua321-cloud/EduscoreAnalytics.git
cd EduscoreAnalytics

# 2. Install dependencies
sudo apt update
sudo apt install nginx supervisor python3-pip
pip3 install -r requirements.txt
pip3 install streamlit

# 3. Update supervisor.conf with your actual path
sudo nano supervisor.conf
# Change: /path/to/EduscoreAnalytics
# To: /home/yourusername/EduscoreAnalytics

# 4. Copy supervisor config
sudo cp supervisor.conf /etc/supervisor/conf.d/eduscore.conf

# 5. Update nginx config with YOUR domain
sudo nano nginx_config.conf
# Change all: yourdomain.com
# To: brilliantschool.com (your actual domain)

# 6. Copy nginx config
sudo cp nginx_config.conf /etc/nginx/sites-available/eduscore
sudo ln -s /etc/nginx/sites-available/eduscore /etc/nginx/sites-enabled/

# 7. Test and reload
sudo nginx -t
sudo systemctl reload nginx

# 8. Start applications
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start eduscore_apps:*
```

#### STEP 5: Access Your Production URLs! 🎉

Now you can access your applications from anywhere:

```
Main App:       http://app.brilliantschool.com
Admin:          http://admin.brilliantschool.com
Parents Portal: http://parents.brilliantschool.com
```

**Share these URLs with:**
- Teachers and staff → Main App URL
- School administrators → Admin URL
- Parents → Parents Portal URL

#### STEP 6: Add HTTPS/SSL (Optional but Recommended)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get free SSL certificates
sudo certbot --nginx -d app.brilliantschool.com -d admin.brilliantschool.com -d parents.brilliantschool.com

# Now your URLs will be HTTPS:
# https://app.brilliantschool.com
# https://admin.brilliantschool.com
# https://parents.brilliantschool.com
```

---

## 📱 Accessing from Different Devices

### From Any Device on Internet (Production URLs)
```
✅ Any computer with internet
✅ Any smartphone with browser
✅ Any tablet with browser

Just visit: http://app.yourschool.com (your actual domain)
```

### From Devices on Same WiFi (Development)
```
✅ Your phone connected to same WiFi
✅ Other computers on same network
✅ Tablets on same network

Visit: http://YOUR_COMPUTER_IP:5000
Example: http://192.168.1.100:5000
```

---

## 🆘 Troubleshooting

### Issue: Can't access localhost:5000

**Solution 1:** Check if app is running
```bash
# Check if ports are in use
lsof -i :5000
lsof -i :5001
lsof -i :5002
```

**Solution 2:** Restart the applications
```bash
./stop_all.sh
./start_all.sh
```

### Issue: Production URLs not working

**Solution 1:** Verify DNS is configured
```bash
# Check if DNS is working
nslookup app.yourschool.com
ping app.yourschool.com
```

**Solution 2:** Check nginx is running
```bash
sudo systemctl status nginx
sudo systemctl restart nginx
```

**Solution 3:** Check applications are running
```bash
sudo supervisorctl status
```

### Issue: "Connection Refused" or "Site Can't Be Reached"

**Checklist:**
- [ ] Is the application running? (Check with `ps aux | grep streamlit`)
- [ ] Is nginx running? (`sudo systemctl status nginx`)
- [ ] Is firewall allowing traffic? (`sudo ufw status`)
- [ ] Did you configure DNS correctly?
- [ ] Did you wait 10-30 minutes for DNS to propagate?

---

## 📞 Quick Command Reference

### Development Mode
```bash
# Start all apps
./start_all.sh

# Stop all apps
./stop_all.sh

# Access URLs
http://localhost:5000  # Main App
http://localhost:5001  # Admin
http://localhost:5002  # Parents Portal
```

### Production Mode
```bash
# Check status
sudo supervisorctl status

# Restart all
sudo supervisorctl restart eduscore_apps:*

# View logs
sudo supervisorctl tail -f eduscore_main_app

# Access URLs (replace with your domain)
http://app.yourschool.com
http://admin.yourschool.com
http://parents.yourschool.com
```

---

## 🎓 Summary

**For Testing/Development:**
1. Run `./start_all.sh`
2. Visit `http://localhost:5000`, `http://localhost:5001`, `http://localhost:5002`
3. Done! ✅

**For Production/Real Use:**
1. Buy domain (e.g., `myschool.com`)
2. Get server
3. Add DNS records (app, admin, parents → server IP)
4. Install apps following DEPLOYMENT.md
5. Visit `http://app.myschool.com`, etc.
6. Done! ✅

---

## 🔗 Related Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete production deployment guide
- **[MULTI_ENTRY_POINT_SETUP.md](MULTI_ENTRY_POINT_SETUP.md)** - Configuration reference
- **[ARCHITECTURE.txt](ARCHITECTURE.txt)** - System architecture diagram

---

**Need Help?**
- Developer: Munyua Kamau
- Phone: 0793975959

**Still confused?** Start with Option 1 (Development Mode) - it's the easiest way to see the 3 URLs in action!
