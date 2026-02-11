# Multi-Entry Point Configuration

This document provides a quick reference for the multi-entry point setup of EdusCore Analytics.

## 🎯 Quick Start

### Development Mode

Start all three applications:
```bash
./start_all.sh
```

Stop all applications:
```bash
./stop_all.sh
```

### Access URLs (Development)
- **Main App**: http://localhost:5000
- **Admin Features**: http://localhost:5001
- **Parents Portal**: http://localhost:5002

### Access URLs (Production)
- **Main App**: http://app.yourdomain.com
- **Admin Features**: http://admin.yourdomain.com
- **Parents Portal**: http://parents.yourdomain.com

## 📁 Configuration Files

| File | Purpose |
|------|---------|
| `admin_features.py` | Admin dashboard entry point (port 5001) |
| `parents_portal_standalone.py` | Parents portal entry point (port 5002) |
| `supervisor.conf` | Process manager configuration for production |
| `nginx_config.conf` | Nginx reverse proxy configuration |
| `start_all.sh` | Development startup script |
| `stop_all.sh` | Development shutdown script |
| `DEPLOYMENT.md` | Complete deployment documentation |

## 🚀 Deployment

For complete deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).

### Quick Production Setup

1. **Install dependencies:**
   ```bash
   sudo apt install nginx supervisor
   pip install -r requirements.txt
   ```

2. **Configure Supervisor:**
   ```bash
   sudo cp supervisor.conf /etc/supervisor/conf.d/eduscore.conf
   # Edit paths in the file
   sudo supervisorctl reread
   sudo supervisorctl update
   ```

3. **Configure Nginx:**
   ```bash
   sudo cp nginx_config.conf /etc/nginx/sites-available/eduscore
   # Edit domain names in the file
   sudo ln -s /etc/nginx/sites-available/eduscore /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. **Configure DNS:**
   - Point `app.yourdomain.com` to your server IP
   - Point `admin.yourdomain.com` to your server IP
   - Point `parents.yourdomain.com` to your server IP

## 🔧 Management Commands

### Supervisor (Production)
```bash
# Check status
sudo supervisorctl status

# Start all
sudo supervisorctl start eduscore_apps:*

# Stop all
sudo supervisorctl stop eduscore_apps:*

# Restart all
sudo supervisorctl restart eduscore_apps:*

# View logs
sudo supervisorctl tail -f eduscore_main_app
```

### Manual (Development)
```bash
# Start individual app
streamlit run app.py --server.port 5000
streamlit run admin_features.py --server.port 5001
streamlit run parents_portal_standalone.py --server.port 5002

# Check running processes
ps aux | grep streamlit

# Check ports
sudo lsof -i :5000
sudo lsof -i :5001
sudo lsof -i :5002
```

## 📊 Application Overview

### Main Application (app.py)
- **Port**: 5000
- **Purpose**: Primary exam management and analysis interface
- **Users**: Teachers, administrators, staff
- **Features**: Exam entry, analysis, report generation

### Admin Features (admin_features.py)
- **Port**: 5001
- **Purpose**: Administrative dashboard
- **Users**: Administrators only
- **Features**: School management, user management, system configuration

### Parents Portal (parents_portal_standalone.py)
- **Port**: 5002
- **Purpose**: Parent-facing portal
- **Users**: Parents/guardians
- **Features**: View student performance, download report cards, update contact info

## 🔒 Security Notes

- All applications require authentication
- Admin Features checks for admin privileges
- Parents Portal operates in restricted mode
- Use HTTPS in production (see DEPLOYMENT.md for SSL setup)

## 🆘 Troubleshooting

### Port Already in Use
```bash
# Kill process on port
sudo lsof -ti:5000 | xargs kill -9
sudo lsof -ti:5001 | xargs kill -9
sudo lsof -ti:5002 | xargs kill -9
```

### Application Not Starting
```bash
# Check logs (development)
cat logs/app.log
cat logs/admin_features.log
cat logs/parents_portal.log

# Check logs (production)
sudo tail -f /var/log/supervisor/eduscore_*.log
```

### Nginx Issues
```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Restart nginx
sudo systemctl restart nginx
```

## 📚 Additional Resources

- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [README.md](README.md) - Main project documentation

---

**Developer:** Munyua Kamau | **Phone:** 0793975959
