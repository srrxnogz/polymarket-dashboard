# Polymarket Bot · panel (simulación)

Página de Streamlit de solo lectura que muestra el bot en modo simulación (paper trading).
Solo contiene la interfaz.

- `main`: código de la página (`streamlit_app.py`, archivo principal en Streamlit).

Para datos en directo (cada 15 s) pon en **Secrets** un token de GitHub (cualquiera sirve: los tokens siempre pueden
leer repos públicos). Sin token la página lee la copia en caché de GitHub, con hasta 5 min de retraso:
```toml
TELEMETRY_URL = "https://api.github.com/repos/srrxnogz/polymarket-dashboard/contents/telemetry_snapshot.json?ref=telemetry"
GITHUB_TOKEN = "<token de GitHub>"
```
- `telemetry`: `telemetry_snapshot.json`, actualizado por el bot cada 15 s.
