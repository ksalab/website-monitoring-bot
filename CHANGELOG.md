# Changelog

All notable changes to this project will be documented in this file.
The format is based on Keep a Changelog,and this project adheres to Semantic Versioning.

## [UNTAGGED]

## [0.5.0] - 2025-06-12

### Added

- feat(notifications): add multiple DOMAIN_EXPIRY_THRESHOLD values (30,15,7,1)
- feat(notifications): add SSL_EXPIRY_THRESHOLD with values (30,15,7,1)

## [0.4.0] - 2025-06-12

### Added

- feat(domain): add domain expiration monitoring with WHOIS
- feat(notifications): send domain expiration warnings based on DOMAIN_EXPIRY_THRESHOLD

## [0.3.0] - 2025-06-12

### Added

- feat(sites): move sites.json to /data and extend format with ssl_valid, ssl_expires, domain_expires
- feat(sites): update sites.json with check results

## [0.2.0] - 2025-06-11

### Fixed

- fix(bot): some bugs

## [0.1.0] - 2025-06-11

### Added

- Initial implementation of the Telegram bot for website monitoring.
- Support for HTTP status and SSL certificate checks.
- Telegram commands: /start, /status.
- Configuration via .env and sites.json.
- Logging to bot.log and console.

