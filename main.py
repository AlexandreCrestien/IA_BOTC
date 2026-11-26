"""Lance le serveur du jeu : http://127.0.0.1:8000

La base doit tourner avant (docker compose up -d, voir le README) : sinon, message clair et arrêt,
plutôt qu'une longue erreur technique au démarrage du serveur.
"""
import sys

import uvicorn

from backend.db.database import DatabaseUnavailable, check_database

if __name__ == "__main__":
    try:
        check_database()
    except DatabaseUnavailable as error:
        print(f"\n{error}\n", file=sys.stderr)
        sys.exit(1)
    uvicorn.run("backend.server.app:app", host="127.0.0.1", port=8000, reload=True)
