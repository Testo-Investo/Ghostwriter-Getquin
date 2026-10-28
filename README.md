# Ghostwriter – Vertriebsagent

Agent, der im Namen von Marc Knieb Kunden in Teams passende Produkte aus der
Excel-Produktliste anbietet, plus Dashboard zur Nachverfolgung.
Projektkontext und Entscheidungen: [CLAUDE.md](CLAUDE.md).

**Status: Phase 1 – nur lesend.** Es werden noch keine Nachrichten gesendet.

Einrichtung: [docs/SETUP_AZURE.md](docs/SETUP_AZURE.md)

```bash
pip install -r requirements.txt
cp .env.example .env
python -m agent.cli whoami
python -m agent.cli catalog
python -m agent.cli export-chats
```
