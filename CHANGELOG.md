# Changelog

All notable changes to this project will be documented in this file.
The format is based on Keep a Changelog,and this project adheres to Semantic Versioning.

## [UNTAGGED]

## [1.4.3] - 2025-06-15

### Fixed

- fix(handlers): Restore f-strings in logs and messages for improved readability

## [1.4.2] - 2025-06-15

### Added

- feat(handlers): Add "Cancel" inline button to exit URL input state after pressing "Add site" in `/listsites`
- feat(handlers): Add command handling in AddSiteState.url to reset state and re-dispatch commands

### Fixed

- fix(handlers): Correct import typo load_sitsites to load_sites
- fix(handlers): Translate all comments, messages, and logs to English

## [1.4.1] - 2025-06-15

### Added

- feat(handlers): Add FSM for interactive URL input after pressing "Add site" button in /listsites

## [1.4.0] - 2025-06-15

### Added

- feat(handlers): Add `/addsite <url>` command to add new websites to monitoring with URL validation
- feat(handlers): Add "Add site" inline button to `/listsites` response with callback to prompt `/addsite`

## [1.3.2] - 2025-06-13

### Fixed

- fix(handlers): Correct registrar_info hyperlink in `/status` to display registrar name as clickable link using text_link entity

## [1.3.1] - 2025-06-13

### Fixed

- fix(handlers): Correct aiogram.utils.formatting usage in `/status` to avoid tuple error by unifying content with as_line

## [1.3.0] - 2025-06-13

### Added

- feat(handlers): Use aiogram.utils.formatting for `/status` and `/listsites` to simplify message formatting with entities

### Fixed

- fix(handlers): Resolve MarkdownV2 parsing errors in `/status` by replacing manual escaping with aiogram formatting
- fix(handlers): Improve logging for `/status` with rendered text and entities

## [1.2.4] - 2025-06-13

### Fixed

- fix(handlers): Ensure strict MarkdownV2 escaping for all string fields in /status to handle special characters like '.'
- fix(handlers): Add detailed field-level logging in `/status` to identify MarkdownV2 issues

## [1.2.3] - 2025-06-13

### Fixed

- fix(handlers): Improve MarkdownV2 escaping in `/status` to handle all special characters in URLs, status, and registrar fields
- fix(handlers): Add debug logging for `/status` message content to aid troubleshooting

## [1.2.2] - 2025-06-13

### Added

- feat(handlers): Send separate `/status` messages for each site to isolate errors

### Fixed

- fix(handlers): Correct MarkdownV2 escaping for Registrar hyperlink in `/status` to handle all special characters
- fix(handlers): Ensure `/status` processes each site independently to prevent errors from affecting other sites

## [1.2.1] - 2025-06-13

### Fixed

- fix(handlers): Correct Registrar display in `/status` to use hyperlink for registrar_url and handle lists, missing URLs, and missing registrars

## [1.2.0] - 2025-06-13

### Added

- feat(handlers): Improve `/status` message format with separated SSL and Domain blocks
- feat(handlers): Add status emojis (🟢 for 200, 🔴 for errors) in `/status` output
- feat(checks): Add registrar name and URL to domain status in `/status`
- feat(handlers): Display registrar as Registrar: [name] ([url]) in `/status`

## [1.1.0] - 2025-06-13

### Added

- feat(storage): Implement per-user site files (`data/<user_id>.json`)
- feat(notifications): Update monitoring to handle sites for all users
- feat(handlers): Pass user_id to load/save sites in `/status` and `/listsites`

### Removed

- feat(storage): Remove usage of `data/sites.json`
- feat(config): Remove SITES_PATH constant

## [1.0.0] - 2025-06-13

### Fixed

- fix(domain): Correct domain expiration handling to update expiry date on successful WHOIS queries
- fix(status): Always perform WHOIS queries for `/status` command to ensure up-to-date domain expiration data
- fix(notifications): Handle WHOIS errors gracefully, showing cached data with error message
- fix(handlers): Improve `/status` output to indicate WHOIS errors with last checked date

## [0.9.0] - 2025-06-10

### Added

- feat(refactor): split code into modules under `modules/` (config, logging, storage, checks, notifications, handlers)
- feat(refactor): improve code readability with PEP 8 and best practices
- refactor(config): move constants to config module
- refactor(logging): centralize logging setup
- refactor(storage): separate sites.json handling
- refactor(checks): modularize HTTP, SSL, and domain checks
- refactor(notifications): encapsulate monitoring logic
- refactor(handlers): organize command handlers

## [0.8.0] - 2025-06-12

### Added

- feat(logging): move logs to `logs/` directory
- feat(logging): implement log rotation with compression (.gz)
- feat(logging): enhance log informativeness for operations

### Fixed

- fix(code): correct save(sites) to save(sites) (repeated issue)

## [0.7.0] - 2025-06-12

### Added

- feat(commands): add `/listsites` command to list monitored websites

### Fixed

- fix(code): correct save(sites) to save_sites(sites)
- fix(logging): comment out verbose config loading logs

## [0.6.0] - 2025-06-12

### Added

- feat(notifications): add NOTIFICATION_MODE (group/user) with USER_ID support
- feat(notifications): remove startup message

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

- feat(sites): move sites.json to `/data` and extend format with ssl_valid, ssl_expires, domain_expires
- feat(sites): update sites.json with check results

## [0.2.0] - 2025-06-11

### Fixed

- fix(bot): some bugs

## [0.1.0] - 2025-06-11

### Added

- Initial implementation of the Telegram bot for website monitoring.
- Support for HTTP status and SSL certificate checks.
- Telegram commands: `/start`, `/status`.
- Configuration via `.env` and `sites.json`.
- Logging to `bot.log` and console.

