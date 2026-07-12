---
title: Linux Server Diagnostic GPT Privacy Policy
---

# Linux Server Diagnostic GPT Privacy Policy

Effective date: 2026-07-13

## Overview

Linux Server Diagnostic GPT is a personal monitoring assistant. It retrieves the current operational status of one self-managed Linux server through a read-only diagnostic API and explains that status in Japanese.

## Data processed

When the Action is used, the service processes the following server-monitoring data:

- server reachability
- CPU, memory, and disk usage percentages
- load average, uptime, and metric observation time
- API request metadata required to operate and secure the service

The Action does not provide shell access, execute commands on the server, change server settings, or accept arbitrary PromQL queries.

## Purpose and sharing

The data is used only to retrieve and explain the monitored server's current status. The service uses ChatGPT to invoke the Action and AWS services, including API Gateway, Lambda, Amazon Managed Service for Prometheus, Systems Manager Parameter Store, and CloudWatch Logs, to authenticate and process the request.

The diagnostic API is protected by a shared secret. The secret is not included in API responses, source code, or application logs.

## Retention

- AMP monitoring metrics are retained for 180 days.
- CloudWatch Logs created for the diagnostic API are retained for 14 days.
- The operator does not intentionally collect a user profile, account identifier, or user-provided free-text input through the diagnostic API.

## Security and access

The API is read-only and accepts only the fixed `home-server` monitoring target. Access requires a valid API shared secret. No security measure can guarantee absolute protection; do not share the GPT or its access credentials with people who should not be able to view the monitored server's status.

## Changes and contact

This policy may be updated when the service changes. The latest version is published at this URL.

For questions or requests about this policy, open an issue in the [linux-monitoring-gpt repository](https://github.com/Reotech736/linux-monitoring-gpt/issues).
