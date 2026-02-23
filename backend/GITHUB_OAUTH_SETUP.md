# GitHub OAuth (conexión por proyecto)

Para que cada **proyecto** pueda vincular su propia cuenta de GitHub (como en AWS o Vercel), se usa OAuth: el usuario autoriza solo ese proyecto y el token se guarda en la base de datos, no un token global.

## 1. Crear una OAuth App en GitHub

1. Entra en **GitHub** → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App**.
2. **Application name**: por ejemplo `Project Anatomy` (o el nombre de tu producto).
3. **Homepage URL**: URL de tu frontend (ej. `http://localhost:5173` o `https://tu-dominio.com`).
4. **Authorization callback URL**: debe ser la URL del backend + `/api/auth/github/callback`:
   - Local: `http://localhost:8000/api/auth/github/callback`
   - Producción: `https://api.tu-dominio.com/api/auth/github/callback`
5. Guarda. Copia **Client ID** y genera un **Client secret**.

## 2. Configurar el backend

En el `.env` del backend:

```env
GITHUB_CLIENT_ID=tu_client_id
GITHUB_CLIENT_SECRET=tu_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
FRONTEND_URL=http://localhost:5173
```

- **GITHUB_REDIRECT_URI**: debe coincidir exactamente con la “Authorization callback URL” de la OAuth App (mismo origen y path).
- **FRONTEND_URL**: URL del frontend; tras conectar GitHub el usuario se redirige aquí con `?github_connected=1&project_id=...`.

## 3. Flujo en la app

1. El usuario crea o edita un proyecto y pone una **URL de repo de GitHub** (y rama).
2. En el detalle del proyecto (Step 1) aparece **“Connect GitHub account”**.
3. Al hacer clic, se redirige a GitHub para que autorice el acceso a sus repos.
4. GitHub redirige al backend `/api/auth/github/callback` con un `code`; el backend lo cambia por un `access_token` y lo guarda **solo para ese proyecto** en la base de datos.
5. El usuario vuelve al frontend con “GitHub connected” y puede ejecutar el análisis (incluidos repos privados a los que tenga acceso).

Cada proyecto tiene su propio token; no se usa un token global compartido. Así se puede convertir en SaaS: cada usuario/conversación puede tener su propio proyecto y su propia conexión GitHub.

## 4. Desconectar

En Step 1, si ya hay “GitHub account connected”, aparece **Disconnect** para borrar el token de ese proyecto. Luego se puede volver a conectar (por ejemplo con otra cuenta).
