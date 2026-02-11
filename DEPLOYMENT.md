# EdusCore Analytics - Multi-Entry Point Deployment Guide

This guide explains how to deploy EdusCore Analytics with three separate entry points accessible via different URLs using subdomain-based routing.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Development Setup](#development-setup)
5. [Production Deployment](#production-deployment)
6. [Managing Applications](#managing-applications)
7. [DNS Configuration](#dns-configuration)
8. [SSL Setup](#ssl-setup)
9. [Troubleshooting](#troubleshooting)
10. [Monitoring](#monitoring)

---

## 🎯 Overview

EdusCore Analytics is deployed with three separate entry points:

| Entry Point | Port | Subdomain | Description |
|------------|------|-----------|-------------|
| Main App | 5000 | app.yourdomain.com | Primary exam management interface |
| Admin Features | 5001 | admin.yourdomain.com | Administrative dashboard |
| Parents Portal | 5002 | parents.yourdomain.com | Parent-facing portal |

---

## 📦 Prerequisites

### Required Software

1. **Python 3.8+**
   ```bash
   python3 --version
   ```

2. **Streamlit**
   ```bash
   pip install streamlit
   # Or install all dependencies
   pip install -r requirements.txt
   ```

3. **Nginx** (for production)
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install nginx
   
   # CentOS/RHEL
   sudo yum install nginx
   ```

4. **Supervisor** (for production)
   ```bash
   # Ubuntu/Debian
   sudo apt install supervisor
   
   # CentOS/RHEL
   sudo yum install supervisor
   ```

5. **lsof** (for port checking in scripts)
   ```bash
   # Ubuntu/Debian
   sudo apt install lsof
   
   # CentOS/RHEL
   sudo yum install lsof
   ```

### System Requirements

- **RAM**: Minimum 2GB (4GB recommended)
- **CPU**: 2 cores minimum
- **Disk**: 5GB free space
- **OS**: Linux (Ubuntu 20.04+ recommended)

---

## 🏗️ Architecture

```
                          Internet
                              |
                          [Nginx]
                    Reverse Proxy
                    Port 80/443
                              |
         +--------------------+--------------------+
         |                    |                    |
   app.yourdomain.com  admin.yourdomain.com  parents.yourdomain.com
         |                    |                    |
      [Streamlit]          [Streamlit]          [Streamlit]
      app.py:5000     admin_features.py:5001  parents_portal:5002
         |                    |                    |
         +--------------------+--------------------+
                              |
                    [Supervisor Process Manager]
```

### Key Components

1. **Nginx**: Reverse proxy handling external requests and SSL termination
2. **Supervisor**: Process manager ensuring apps restart on failure
3. **Streamlit Apps**: Three separate Python applications on different ports
4. **DNS**: Subdomain routing to the server

---

## 🚀 Development Setup

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd EduscoreAnalytics
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start all applications**
   ```bash
   ./start_all.sh
   ```

4. **Access the applications**
   - Main App: http://localhost:5000
   - Admin Features: http://localhost:5001
   - Parents Portal: http://localhost:5002

### Manual Start (Alternative)

Start each application individually:

```bash
# Terminal 1 - Main Application
streamlit run app.py --server.port 5000

# Terminal 2 - Admin Features
streamlit run admin_features.py --server.port 5001

# Terminal 3 - Parents Portal
streamlit run parents_portal_standalone.py --server.port 5002
```

### Stop All Services

```bash
./stop_all.sh
```

Or manually:
```bash
kill $(cat logs/*.pid)
```

---

## 🌐 Production Deployment

### Step 1: Prepare the Server

1. **Update system**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Create application user**
   ```bash
   sudo useradd -m -s /bin/bash eduscore
   sudo usermod -aG www-data eduscore
   ```

3. **Set up application directory**
   ```bash
   sudo mkdir -p /var/www/eduscore
   sudo chown eduscore:www-data /var/www/eduscore
   ```

4. **Clone repository**
   ```bash
   cd /var/www/eduscore
   sudo -u eduscore git clone <repository-url> .
   ```

5. **Install Python dependencies**
   ```bash
   cd /var/www/eduscore
   sudo -u eduscore python3 -m venv venv
   sudo -u eduscore ./venv/bin/pip install -r requirements.txt
   ```

### Step 2: Configure Supervisor

1. **Update supervisor.conf with correct paths**
   ```bash
   sudo cp supervisor.conf /etc/supervisor/conf.d/eduscore.conf
   ```

2. **Edit the configuration** (replace `/path/to/EduscoreAnalytics` with actual path)
   ```bash
   sudo nano /etc/supervisor/conf.d/eduscore.conf
   ```
   
   Update these lines in all three program sections:
   ```ini
   directory=/var/www/eduscore
   command=/var/www/eduscore/venv/bin/streamlit run app.py ...
   ```

3. **Create log directory**
   ```bash
   sudo mkdir -p /var/log/supervisor
   sudo chown -R eduscore:www-data /var/log/supervisor
   ```

4. **Reload supervisor**
   ```bash
   sudo supervisorctl reread
   sudo supervisorctl update
   sudo supervisorctl start eduscore_apps:*
   ```

### Step 3: Configure Nginx

1. **Copy nginx configuration**
   ```bash
   sudo cp nginx_config.conf /etc/nginx/sites-available/eduscore
   ```

2. **Edit configuration** (replace `yourdomain.com` with your actual domain)
   ```bash
   sudo nano /etc/nginx/sites-available/eduscore
   ```

3. **Enable the site**
   ```bash
   sudo ln -s /etc/nginx/sites-available/eduscore /etc/nginx/sites-enabled/
   ```

4. **Test nginx configuration**
   ```bash
   sudo nginx -t
   ```

5. **Remove default site** (optional)
   ```bash
   sudo rm /etc/nginx/sites-enabled/default
   ```

6. **Reload nginx**
   ```bash
   sudo systemctl reload nginx
   ```

### Step 4: Configure Firewall

```bash
# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw enable
```

---

## 🌍 DNS Configuration

Configure DNS records for your subdomains:

### A Records

Point all subdomains to your server's IP address:

```
Type    Name        Value           TTL
A       app         your.server.ip  300
A       admin       your.server.ip  300
A       parents     your.server.ip  300
```

### Alternative: Wildcard Record

```
Type    Name    Value           TTL
A       *       your.server.ip  300
```

### Verify DNS Propagation

```bash
# Check if DNS is working
nslookup app.yourdomain.com
nslookup admin.yourdomain.com
nslookup parents.yourdomain.com

# Or use dig
dig app.yourdomain.com
```

---

## 🔒 SSL Setup

### Using Let's Encrypt (Certbot)

1. **Install Certbot**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   ```

2. **Obtain certificates for all subdomains**
   ```bash
   sudo certbot --nginx -d app.yourdomain.com -d admin.yourdomain.com -d parents.yourdomain.com
   ```

3. **Automatic renewal test**
   ```bash
   sudo certbot renew --dry-run
   ```

### Manual SSL Configuration

1. **Obtain SSL certificates** for each subdomain

2. **Uncomment SSL sections** in `/etc/nginx/sites-available/eduscore`

3. **Update certificate paths**
   ```nginx
   ssl_certificate /path/to/fullchain.pem;
   ssl_certificate_key /path/to/privkey.pem;
   ```

4. **Reload nginx**
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

---

## 🎮 Managing Applications

### Using Supervisor

**Check status**
```bash
sudo supervisorctl status
```

**Start all apps**
```bash
sudo supervisorctl start eduscore_apps:*
```

**Stop all apps**
```bash
sudo supervisorctl stop eduscore_apps:*
```

**Restart all apps**
```bash
sudo supervisorctl restart eduscore_apps:*
```

**Start/stop individual app**
```bash
sudo supervisorctl start eduscore_main_app
sudo supervisorctl stop eduscore_admin_features
sudo supervisorctl restart eduscore_parents_portal
```

**View logs**
```bash
sudo supervisorctl tail -f eduscore_main_app
sudo supervisorctl tail -f eduscore_admin_features
sudo supervisorctl tail -f eduscore_parents_portal
```

### Manual Management

**Check running processes**
```bash
ps aux | grep streamlit
```

**Check ports**
```bash
sudo netstat -tlnp | grep -E '5000|5001|5002'
# Or using lsof
sudo lsof -i :5000
sudo lsof -i :5001
sudo lsof -i :5002
```

---

## 🔧 Troubleshooting

### Applications Not Starting

**Check supervisor logs**
```bash
sudo tail -f /var/log/supervisor/eduscore_main_app.log
sudo tail -f /var/log/supervisor/eduscore_admin_features.log
sudo tail -f /var/log/supervisor/eduscore_parents_portal.log
```

**Check if ports are available**
```bash
sudo lsof -i :5000
sudo lsof -i :5001
sudo lsof -i :5002
```

**Verify Python dependencies**
```bash
cd /var/www/eduscore
./venv/bin/pip list
./venv/bin/python3 -c "import streamlit; print(streamlit.__version__)"
```

### Nginx Issues

**Test configuration**
```bash
sudo nginx -t
```

**Check nginx error logs**
```bash
sudo tail -f /var/log/nginx/error.log
```

**Verify nginx is running**
```bash
sudo systemctl status nginx
```

**Restart nginx**
```bash
sudo systemctl restart nginx
```

### DNS Issues

**Test DNS resolution**
```bash
nslookup app.yourdomain.com
ping app.yourdomain.com
```

**Check /etc/hosts** (for local testing)
```bash
# Add these lines temporarily
127.0.0.1 app.yourdomain.com
127.0.0.1 admin.yourdomain.com
127.0.0.1 parents.yourdomain.com
```

### Port Conflicts

**Kill process on specific port**
```bash
sudo lsof -ti:5000 | xargs kill -9
sudo lsof -ti:5001 | xargs kill -9
sudo lsof -ti:5002 | xargs kill -9
```

### Permission Issues

**Fix ownership**
```bash
sudo chown -R eduscore:www-data /var/www/eduscore
sudo chmod -R 755 /var/www/eduscore
```

**Check file permissions**
```bash
ls -la /var/www/eduscore
```

### SSL Certificate Issues

**Check certificate expiry**
```bash
sudo certbot certificates
```

**Force renewal**
```bash
sudo certbot renew --force-renewal
```

---

## 📊 Monitoring

### Application Health

**Create a monitoring script**
```bash
#!/bin/bash
# monitor.sh

for port in 5000 5001 5002; do
    if curl -s http://localhost:$port/_stcore/health > /dev/null; then
        echo "Port $port: OK"
    else
        echo "Port $port: DOWN"
    fi
done
```

### Log Rotation

**Configure logrotate**
```bash
sudo nano /etc/logrotate.d/eduscore
```

```
/var/log/supervisor/eduscore*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    copytruncate
}
```

### Resource Monitoring

**Check resource usage**
```bash
# CPU and memory
ps aux | grep streamlit

# Detailed monitoring
top -p $(pgrep -d',' streamlit)

# Or use htop
sudo apt install htop
htop -p $(pgrep -d',' streamlit)
```

---

## 🔄 Updating the Application

1. **Stop all services**
   ```bash
   sudo supervisorctl stop eduscore_apps:*
   ```

2. **Pull latest changes**
   ```bash
   cd /var/www/eduscore
   sudo -u eduscore git pull
   ```

3. **Update dependencies**
   ```bash
   sudo -u eduscore ./venv/bin/pip install -r requirements.txt
   ```

4. **Restart services**
   ```bash
   sudo supervisorctl start eduscore_apps:*
   ```

---

## 🆘 Getting Help

### Check Logs

1. **Supervisor logs**: `/var/log/supervisor/`
2. **Nginx logs**: `/var/log/nginx/`
3. **Application logs**: `logs/` directory (development)

### Common Commands Reference

```bash
# Supervisor
sudo supervisorctl status
sudo supervisorctl restart eduscore_apps:*

# Nginx
sudo systemctl status nginx
sudo nginx -t
sudo systemctl reload nginx

# Logs
sudo tail -f /var/log/supervisor/eduscore_main_app.log
sudo tail -f /var/log/nginx/error.log

# Ports
sudo lsof -i :5000
sudo netstat -tlnp | grep 5000
```

---

## 📝 Notes

- **Backup regularly**: Set up automated backups of the application data
- **Monitor resources**: Watch CPU and memory usage, especially under load
- **Update regularly**: Keep all software up to date for security
- **Test before deploying**: Always test changes in development first
- **Document changes**: Keep track of custom configurations

---

## 👥 Support

**Developer:** Munyua Kamau  
**Phone:** 0793975959

For issues or questions, please contact the developer or refer to the application documentation.

---

*Last Updated: February 2025*
