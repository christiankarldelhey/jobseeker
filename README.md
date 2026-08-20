# JobWatch

Monitorea las APIs públicas de los ATS (Greenhouse, Lever, Ashby, Workable,
Recruitee, SmartRecruiters, Personio) de una lista de empresas objetivo,
puntúa las ofertas nuevas según tu perfil, y te avisa por email.

**Importante — límite real de cobertura:** esto solo te da ventaja de
velocidad sobre LinkedIn/Indeed para las empresas que (a) agregaste a
`registry.yaml` y (b) usan uno de estos 7 ATS. No cubre empresas con otro
ATS (iCIMS, Taleo, SuccessFactors, BambooHR, Teamtailor, etc.) ni empresas
que publican nativo en LinkedIn sin ATS externo — para esas, LinkedIn sigue
siendo tu única fuente.

## Setup local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completá tus credenciales SMTP
```

Para Gmail: activá verificación en 2 pasos y generá un
[App Password](https://myaccount.google.com/apppasswords). No uses tu
contraseña normal, Gmail la va a rechazar.

## Uso

```bash
# Correr el poller una vez (fetch + diff + notificación inmediata)
python -m jobwatch.run

# Enviar el digest diario de ofertas de score medio acumuladas
python -m jobwatch.digest

# Intentar resolver (ats, token) para nuevas empresas a partir de su dominio
python -m jobwatch.discover empresa1.com empresa2.com
```

## Configuración

- **`registry.yaml`**: lista de empresas a monitorear (`company`, `ats`, `token`).
  Agregalas a mano o con `jobwatch.discover`. Lo que no se resuelva cae en
  `unresolved.csv` para revisar manualmente.
- **`config.yaml`**: perfil de búsqueda — keywords de stack/seniority/geo con
  pesos, exclusiones duras (junior, becario, stacks no deseados), y umbrales
  de score para notificación inmediata vs digest diario. Editalo libremente,
  no requiere tocar código Python.

## Cómo funciona

1. `jobwatch.run` recorre `registry.yaml`, llama al adapter correspondiente
   por cada empresa, y compara los IDs de oferta contra lo guardado en
   `jobwatch.db` (SQLite).
2. Las ofertas nuevas se puntúan con `match.py` según `config.yaml`.
   Score alto → email inmediato. Score medio → se acumulan para el digest
   diario. Score bajo o excluidas → solo quedan registradas en la DB.
3. `jobwatch.digest` (pensado para correr una vez al día) envía el resumen
   de las ofertas de score medio acumuladas.
4. La tabla `runs` en la DB registra cada corrida (ok/error/cantidad) por
   empresa, para detectar si un token dejó de funcionar silenciosamente
   (p. ej. la empresa cambió de ATS).

## Deploy en GitHub Actions

El workflow `.github/workflows/poll.yml` corre el poller cada 30 min y el
digest una vez al día, y commitea `jobwatch.db` de vuelta al repo para
persistir el estado entre corridas.

Configurá estos **secrets** en el repo (Settings → Secrets and variables → Actions):

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `NOTIFY_EMAIL_TO`
- `NOTIFY_EMAIL_FROM`

## Fuentes soportadas (ATS)

| ATS             | Endpoint                                                              |
|-----------------|------------------------------------------------------------------------|
| Greenhouse      | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`         |
| Lever           | `api.lever.co/v0/postings/{token}?mode=json`                           |
| Ashby           | `api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` |
| Workable        | `apply.workable.com/api/v1/widget/accounts/{token}`                    |
| Recruitee       | `{token}.recruitee.com/api/offers/`                                    |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{token}/postings`                |
| Personio        | `{token}.jobs.personio.de/xml` (XML)                                   |

Todos son endpoints públicos, sin autenticación.

## Explícitamente fuera de alcance

No hay auto-apply. Este bot solo detecta y notifica — el envío de
candidaturas lo hacés vos, a propósito (postular en volumen automatizado
perjudica más de lo que ayuda a perfiles senior/especializados).

## Roadmap sugerido

- [ ] Expandir `registry.yaml` a 100-200 empresas vía `jobwatch.discover`.
- [ ] Migrar la DB a Supabase si el repo empieza a pesar por los commits automáticos.
- [ ] Agregar más canales de notificación (Telegram/Slack) reusando `notify.py` como interfaz.
