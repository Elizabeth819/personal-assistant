# Security Policy

## Reporting

If you find a vulnerability, **do not open a public issue**. Email the maintainer
or use GitHub's private vulnerability reporting on this repo.

## Scope

This project runs on your **own** machine and talks to your **own** Azure OpenAI
deployment. There is no hosted multi-tenant service to attack. That said:

- The FastAPI server binds `0.0.0.0` by default for LAN access — keep it off
  untrusted networks. Add an auth middleware if you want to expose it.
- WebDriverAgent gives full UI control of the tethered iPhone. Treat the WDA
  port (8100) as sensitive.
- `.env` holds your Azure key. It's gitignored — keep it that way.
