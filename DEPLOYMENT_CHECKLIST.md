# Deployment Checklist

Use this checklist to ensure a smooth deployment of the Caller-ID Rotation API.

## Pre-Deployment

### Server Requirements
- [ ] Ubuntu 24.04 LTS (or compatible Linux)
- [ ] Minimum 4GB RAM
- [ ] Minimum 2 CPU cores
- [ ] 20GB+ disk space available
- [ ] Root or sudo access
- [ ] Domain name configured (if using Plesk)

### Software Installation
- [ ] Docker installed (20.10+)
- [ ] Docker Compose installed (2.0+)
- [ ] Plesk installed (optional, for reverse proxy)
- [ ] Git installed (if cloning from repo)

## Initial Setup

### 1. Project Files
- [ ] Project files copied to `/opt/callerid-api`
- [ ] Correct ownership set (`chown $USER:$USER`)
- [ ] Directory permissions verified

### 2. Environment Configuration
- [ ] `.env.example` copied to `.env`
- [ ] `SECRET_KEY` generated and set (use `openssl rand -hex 32`)
- [ ] `ADMIN_TOKEN` generated and set (use `openssl rand -hex 32`)
- [ ] `POSTGRES_PASSWORD` set to secure password
- [ ] `REDIS_PASSWORD` set (optional but recommended)
- [ ] Admin token saved securely (you'll need this!)

### 3. Docker Setup
- [ ] `docker-compose.yml` reviewed
- [ ] Port bindings verified (127.0.0.1:8000)
- [ ] Volume paths confirmed
- [ ] Network configuration checked

## Deployment

### 4. Build & Start
- [ ] Run `docker-compose build`
- [ ] Run `docker-compose up -d`
- [ ] Verify all containers running (`docker-compose ps`)
- [ ] Check logs for errors (`docker logs callerid_api`)

### 5. Database Setup
- [ ] Run `docker exec -it callerid_api python3 scripts/init_db.py`
- [ ] Verify tables created
- [ ] Add sample data (optional): `make init-db-sample`
- [ ] Test database connection

### 6. Import Caller-IDs
- [ ] Prepare CSV file with caller-IDs
- [ ] Copy CSV to container or use sample generator
- [ ] Run bulk import: `make import-sample` or manual import
- [ ] Verify caller-IDs in database
- [ ] Check count: `make count-cids`

## Configuration

### 7. Reverse Proxy (Plesk/Nginx)
- [ ] Domain DNS configured
- [ ] Reverse proxy configured to point to 127.0.0.1:8000
- [ ] Proxy headers set correctly
- [ ] Test HTTP access

### 8. SSL Certificate
- [ ] SSL certificate obtained (Let's Encrypt or other)
- [ ] Certificate installed
- [ ] HTTPS working
- [ ] HTTP to HTTPS redirect configured
- [ ] Certificate auto-renewal configured

### 9. Firewall
- [ ] UFW enabled (or equivalent)
- [ ] SSH port open (22)
- [ ] HTTP port open (80)
- [ ] HTTPS port open (443)
- [ ] Plesk admin port open (8443) if applicable
- [ ] Docker ports blocked from external access (8000, 5432, 6379)

## Testing

### 10. API Testing
- [ ] Health check working: `curl http://127.0.0.1:8000/health`
- [ ] Health check via HTTPS: `curl https://your-domain.com/health`
- [ ] Test `/next-cid` endpoint
- [ ] Test with invalid parameters (should fail gracefully)
- [ ] Run test script: `./scripts/test_api.sh`

### 11. Dashboard Testing
- [ ] Dashboard accessible via HTTPS
- [ ] Admin token authentication working
- [ ] Statistics displaying correctly
- [ ] All sections loading
- [ ] Auto-refresh working

### 12. Performance Testing
- [ ] Response time acceptable (< 100ms)
- [ ] Multiple concurrent requests working
- [ ] Rate limiting functioning
- [ ] No errors under load

## VICIdial Integration

### 13. Asterisk Configuration
- [ ] Dialplan code added to `/etc/asterisk/extensions_custom.conf`
- [ ] Dialplan syntax verified
- [ ] API URL correct in dialplan
- [ ] Asterisk reloaded: `asterisk -rx "dialplan reload"`

### 14. Integration Testing
- [ ] Test call with new dialplan
- [ ] Caller-ID properly set
- [ ] API logs show request
- [ ] No errors in Asterisk logs
- [ ] Fallback working if API unavailable

### 15. Campaign Configuration
- [ ] VICIdial campaign configured
- [ ] Campaign using new dialplan
- [ ] Test calls successful
- [ ] Caller-IDs rotating properly

## Monitoring & Maintenance

### 16. Monitoring Setup
- [ ] Dashboard bookmark saved
- [ ] Admin token stored securely
- [ ] Log rotation configured
- [ ] Monitoring schedule established
- [ ] Alert thresholds defined

### 17. Backup Configuration
- [ ] Backup directory created
- [ ] Backup script tested: `make backup`
- [ ] Cron job for automated backups (optional)
- [ ] Backup retention policy defined
- [ ] Restore procedure tested

### 18. Documentation
- [ ] Deployment notes documented
- [ ] Admin token stored in password manager
- [ ] Team members trained
- [ ] Troubleshooting guide reviewed
- [ ] Contact information documented

## Security

### 19. Security Checklist
- [ ] API only accessible via localhost
- [ ] HTTPS enforced (no HTTP access)
- [ ] Strong admin token used (32+ characters)
- [ ] Database password secure
- [ ] No default credentials in use
- [ ] Firewall rules verified
- [ ] Docker containers not exposed publicly
- [ ] Security updates scheduled

### 20. Access Control
- [ ] SSH key-based authentication configured
- [ ] Root login disabled
- [ ] Non-root user for deployment
- [ ] Sudo access limited
- [ ] Failed login monitoring enabled

## Production Readiness

### 21. Performance Optimization
- [ ] API worker count optimized
- [ ] Database connection pool sized
- [ ] Redis memory limit set
- [ ] Rate limits configured appropriately
- [ ] Caller-ID limits set per business needs

### 22. High Availability (Optional)
- [ ] Database backups automated
- [ ] Failover plan documented
- [ ] Recovery time objective (RTO) defined
- [ ] Recovery point objective (RPO) defined

### 23. Compliance (If Applicable)
- [ ] TCPA compliance reviewed
- [ ] Do Not Call (DNC) lists integrated
- [ ] Call recording compliance
- [ ] Data retention policies
- [ ] Privacy policy updated

## Post-Deployment

### 24. Verification
- [ ] All services running: `docker-compose ps`
- [ ] No errors in logs: `docker logs callerid_api`
- [ ] Database healthy: `make db-shell`
- [ ] Redis healthy: `make redis-shell`
- [ ] API health check passing: `curl https://your-domain.com/health`

### 25. Initial Operations
- [ ] First production call successful
- [ ] Caller-ID allocation working
- [ ] Statistics tracking correctly
- [ ] No performance issues
- [ ] Team satisfied with deployment

### 26. Documentation Updates
- [ ] Production URL documented
- [ ] Admin credentials secured
- [ ] Runbook created
- [ ] Escalation procedures defined
- [ ] Knowledge base updated

## Ongoing Maintenance

### 27. Weekly Tasks
- [ ] Check API logs for errors
- [ ] Review dashboard statistics
- [ ] Verify all services running
- [ ] Check disk space usage
- [ ] Review rate limit hits

### 28. Monthly Tasks
- [ ] Review and rotate logs
- [ ] Update Docker images
- [ ] Review caller-ID inventory
- [ ] Analyze usage patterns
- [ ] Review and adjust rate limits

### 29. Quarterly Tasks
- [ ] Security audit
- [ ] Performance review
- [ ] Capacity planning
- [ ] Documentation review
- [ ] Disaster recovery test

## Troubleshooting Reference

### Common Issues
- [ ] API not starting → Check logs: `docker logs callerid_api`
- [ ] Database connection failed → Verify credentials in `.env`
- [ ] No caller-IDs available → Check inventory: `make count-cids`
- [ ] Rate limit exceeded → Adjust in `.env` and restart
- [ ] Dashboard not accessible → Verify admin token

### Support Resources
- [ ] README.md reviewed
- [ ] DEPLOYMENT.md bookmarked
- [ ] VICIDIAL_INTEGRATION.md accessible
- [ ] FAQ.md reviewed
- [ ] API_REFERENCE.md bookmarked

## Sign-Off

### Deployment Team
- [ ] Deployment lead sign-off: _________________ Date: _______
- [ ] Technical lead sign-off: _________________ Date: _______
- [ ] Operations sign-off: _________________ Date: _______

### Notes
```
[Space for deployment notes, issues encountered, special configurations, etc.]





```

---

**Deployment Status:**
- [ ] Pre-production testing complete
- [ ] Production deployment complete
- [ ] Post-deployment verification complete
- [ ] Team training complete
- [ ] Documentation complete

**Go-Live Date:** ________________

**Deployment By:** ________________

**Reviewed By:** ________________

---

## Quick Command Reference

```bash
# Start/Stop
docker-compose up -d
docker-compose down
docker-compose restart

# Logs
docker logs -f callerid_api
make logs

# Database
make db-shell
make count-cids

# Health
make health
curl https://your-domain.com/health

# Backup
make backup

# Import
make import-sample
```

---

**Ready for Production:** ☐ YES  ☐ NO

**If NO, list blockers:**
1. _________________________________
2. _________________________________
3. _________________________________
