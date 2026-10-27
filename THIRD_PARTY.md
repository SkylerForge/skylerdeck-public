# Componentes de terceros

## Incluidos en el repositorio

| Componente | Autor | Licencia | Dónde |
|---|---|---|---|
| Inter (subconjunto latin) | Rasmus Andersson | SIL Open Font License 1.1 | `static/fonts/inter-latin.woff2` |
| Aldrich (subconjunto latin) | Matt McInerney | SIL Open Font License 1.1 | `static/fonts/aldrich-latin.woff2` |

Las dos fuentes vienen de Google Fonts. Texto de la licencia: https://openfontlicense.org

## Se instalan con pip (`requirements.txt`)

| Paquete | Licencia | Para qué |
|---|---|---|
| Flask | BSD-3-Clause | La API y la página del panel |
| waitress | ZPL 2.1 | El servidor web del panel |
| segno | BSD-3-Clause | El código QR de los enlaces en la terminal |
| tzdata | Apache-2.0 | Zonas horarias en sistemas que no las traen |
| PyYAML (solo pruebas) | MIT | Comprobar que las cabeceras son YAML válido |
