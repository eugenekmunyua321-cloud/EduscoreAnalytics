# Step-by-Step Example: Getting Your URLs

This document shows you EXACTLY what you'll see when getting your 3 URLs.

## Example 1: Development Mode (Localhost URLs)

### What You'll Type and See

```bash
$ cd EduscoreAnalytics
$ ./start_all.sh
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════╗
║         EdusCore Analytics - Multi-App Launcher           ║
╚════════════════════════════════════════════════════════════╝

✓ All required files found

Checking for existing processes...

Starting Main Application on port 5000...
✓ Main Application started (PID: 12345)

Starting Admin Features on port 5001...
✓ Admin Features started (PID: 12346)

Starting Parents Portal on port 5002...
✓ Parents Portal started (PID: 12347)

Waiting for services to start...

Verifying services...
✓ Main Application running on http://localhost:5000
✓ Admin Features running on http://localhost:5001
✓ Parents Portal running on http://localhost:5002

════════════════════════════════════════════════════════════
✓ All services started successfully!

Access the applications at:
  • Main App:       http://localhost:5000
  • Admin Features: http://localhost:5001
  • Parents Portal: http://localhost:5002

To stop all services, run: ./stop_all.sh
════════════════════════════════════════════════════════════
```

### What You'll Do Next

**Step 1:** Open your web browser

**Step 2:** Visit the first URL:
```
http://localhost:5000
```

**Step 3:** You'll see the Main Application login page

**Step 4:** Open new tabs for the other URLs:
```
http://localhost:5001  (Admin)
http://localhost:5002  (Parents Portal)
```

### ✅ Result: You now have 3 different URLs working!

---

## Example 2: Production Mode (Custom Domain URLs)

### Scenario
- Your school name: "Brilliant Academy"
- Domain you bought: `brilliantacademy.com`
- Server IP: `203.0.113.45`

### Step 1: Configure DNS

**Login to your domain registrar (e.g., Namecheap)**

Navigate to: Domains → brilliantacademy.com → Advanced DNS

**Click "Add New Record" three times and enter:**

```
Record 1:
  Type: A Record
  Host: app
  Value: 203.0.113.45
  TTL: Automatic

Record 2:
  Type: A Record
  Host: admin
  Value: 203.0.113.45
  TTL: Automatic

Record 3:
  Type: A Record
  Host: parents
  Value: 203.0.113.45
  TTL: Automatic
```

**Save Changes**

### Step 2: Verify DNS (Wait 10-30 minutes, then test)

```bash
$ nslookup app.brilliantacademy.com
```

**Expected Output:**
```
Server:		8.8.8.8
Address:	8.8.8.8#53

Non-authoritative answer:
Name:	app.brilliantacademy.com
Address: 203.0.113.45
```

**Good! DNS is working.** Now test the others:

```bash
$ nslookup admin.brilliantacademy.com
$ nslookup parents.brilliantacademy.com
```

If all three return your server IP, you're ready!

### Step 3: Install on Server

**SSH into your server:**
```bash
$ ssh root@203.0.113.45
```

**Follow installation (from DEPLOYMENT.md):**
```bash
# Clone repository
$ git clone https://github.com/eugenekmunyua321-cloud/EduscoreAnalytics.git
$ cd EduscoreAnalytics

# Install dependencies
$ sudo apt update
$ sudo apt install nginx supervisor python3-pip
$ pip3 install -r requirements.txt
$ pip3 install streamlit

# Configure supervisor
$ sudo nano supervisor.conf
# Change /path/to/EduscoreAnalytics to /root/EduscoreAnalytics
$ sudo cp supervisor.conf /etc/supervisor/conf.d/eduscore.conf

# Configure nginx
$ sudo nano nginx_config.conf
# Change all "yourdomain.com" to "brilliantacademy.com"
$ sudo cp nginx_config.conf /etc/nginx/sites-available/eduscore
$ sudo ln -s /etc/nginx/sites-available/eduscore /etc/nginx/sites-enabled/

# Test and start
$ sudo nginx -t
nginx: configuration file /etc/nginx/nginx.conf test is successful

$ sudo systemctl reload nginx
$ sudo supervisorctl reread
$ sudo supervisorctl update
$ sudo supervisorctl start eduscore_apps:*
```

### Step 4: Access Your URLs!

Open your browser and visit:

```
http://app.brilliantacademy.com
```

**What you'll see:** The main application login page! 🎉

Now try the other URLs:
```
http://admin.brilliantacademy.com
http://parents.brilliantacademy.com
```

### ✅ Result: You now have 3 custom URLs working!

---

## Example 3: Sharing URLs with Users

### For Teachers and Staff
Send them an email:

```
Subject: New EdusCore Analytics System

Dear Teachers,

We've set up the new exam management system!

Access it here:
🔗 http://app.brilliantacademy.com

Use your provided username and password to login.

For support, contact IT department.

Best regards,
Administration
```

### For Administrators
```
Subject: Admin Dashboard Access

Dear Admin Team,

Your admin dashboard is ready:
🔗 http://admin.brilliantacademy.com

This is restricted to administrators only.

Best regards,
IT Department
```

### For Parents
```
Subject: Parents Portal Now Available

Dear Parents,

Track your child's academic progress online!

Visit: 🔗 http://parents.brilliantacademy.com

Login with your provided credentials.

Best regards,
Brilliant Academy
```

---

## Example 4: Troubleshooting

### Problem: "This site can't be reached"

**Test DNS:**
```bash
$ nslookup app.brilliantacademy.com
```

**If it returns your IP:** DNS is working, check server
**If it fails:** DNS not configured or still propagating (wait longer)

### Problem: "Connection refused"

**Check if apps are running:**
```bash
$ sudo supervisorctl status
```

**Expected Output:**
```
eduscore_main_app          RUNNING   pid 12345, uptime 0:05:23
eduscore_admin_features    RUNNING   pid 12346, uptime 0:05:23
eduscore_parents_portal    RUNNING   pid 12347, uptime 0:05:23
```

**If not running:**
```bash
$ sudo supervisorctl start eduscore_apps:*
```

### Problem: Getting 502 Bad Gateway

**Check nginx:**
```bash
$ sudo systemctl status nginx
```

**Check app logs:**
```bash
$ sudo supervisorctl tail -100 eduscore_main_app
```

---

## Real-World Examples from Schools

### Example School 1: St. Mary's High School
```
Domain: stmaryshigh.ac.ke
URLs:
  - app.stmaryshigh.ac.ke      (Teachers)
  - admin.stmaryshigh.ac.ke    (Principal, Admin)
  - parents.stmaryshigh.ac.ke  (Parents)
```

### Example School 2: Greenfield Academy
```
Domain: greenfieldacademy.com
URLs:
  - app.greenfieldacademy.com
  - admin.greenfieldacademy.com
  - parents.greenfieldacademy.com
```

### Example School 3: Tech Valley School (Using IP for testing)
```
Development Setup (no domain yet):
  - http://192.168.1.100:5000  (Main App)
  - http://192.168.1.100:5001  (Admin)
  - http://192.168.1.100:5002  (Parents Portal)

Later moved to:
  - app.techvalley.edu
  - admin.techvalley.edu
  - parents.techvalley.edu
```

---

## Summary: Your Action Plan

### Option A: Just Testing (Start Today!)
1. Run `./start_all.sh`
2. Visit `localhost:5000`, `localhost:5001`, `localhost:5002`
3. Done in 2 minutes! ✅

### Option B: Production Deployment (This Week)
1. **Day 1:** Buy domain ($10)
2. **Day 2:** Get server ($5-10/month)
3. **Day 3:** Configure DNS (3 A records)
4. **Day 4:** Wait for DNS propagation
5. **Day 5:** Install apps on server
6. **Day 6:** Test all 3 URLs
7. **Day 7:** Share URLs with users ✅

---

## Need More Help?

- 📖 **Detailed Guide:** Read [HOW_TO_GET_URLS.md](HOW_TO_GET_URLS.md)
- 🚀 **Deployment Steps:** Read [DEPLOYMENT.md](DEPLOYMENT.md)
- 🎯 **Quick Reference:** Read [QUICK_START_URLS.txt](QUICK_START_URLS.txt)
- 📞 **Support:** Contact developer at 0793975959

---

**Remember:** Start with localhost (development mode) first. It's the easiest way to see everything working before buying a domain!
