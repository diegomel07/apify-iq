# Enriquecimiento de Egresados y Búsqueda de LinkedIn con Apify

Herramientas en Python para buscar, extraer y enriquecer datos de perfiles de LinkedIn a partir de bases de datos de egresados en Excel, utilizando el Actor de Apify [`harvestapi/linkedin-profile-search-by-name`](https://apify.com/harvestapi/linkedin-profile-search-by-name).

---

## 📁 Estructura del Proyecto

* **[`enrich_graduates.py`](file:///Users/diegomellizo/Documents/Code/personal/apify/enrich_graduates.py)**: Script principal para procesar de forma desatendida e incremental el archivo Excel de egresados (`IQ`, `MIQ`, `MIA`, `DIQ`), aplicando filtros de universidad, scoring heurístico y guardado celda por celda.
* **[`test_enrich_graduates.py`](file:///Users/diegomellizo/Documents/Code/personal/apify/test_enrich_graduates.py)**: Suite de pruebas unitarias 100% offline (sin llamadas a Apify) para validar el algoritmo de coincidencia y parseo de nombres.
* **`PAE-Organizacion_Egresados_Enriquecido.xlsx`**: Archivo Excel de salida donde se guardan las URLs de LinkedIn encontradas, preservando el archivo original intacto.

---

## ⚙️ Requisitos previos e Instalación

1. **Python 3.10+**
2. **Crear y activar el entorno virtual:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔑 Autenticación (Tokens de Apify)

El sistema soporta dos métodos automáticos de autenticación:
1. **Detección OAuth automática (sin configuración manual):**  
   Si iniciaste sesión en Antigravity / MCP, los scripts detectan y usan automáticamente tus credenciales guardadas en `~/.mcp-auth/`.
2. **Archivo `.env`:**  
   Copia el archivo de ejemplo y coloca tu token personal de [Apify Integrations Console](https://console.apify.com/settings/integrations):
   ```bash
   cp .env.example .env
   # Edita .env y asigna APIFY_TOKEN=tu_token_aqui
   ```

---

## 🚀 Uso de `enrich_graduates.py` (Enriquecimiento de Excel)

Este script lee las hojas del archivo Excel (`DIQ`, `MIA`, `MIQ`, `IQ`), busca a cada egresado con el filtro de la *Universidad Nacional de Colombia*, evalúa los candidatos con un puntaje de confianza (0 a 100) y escribe la URL en la columna `Perfil LinkedIn`.

### 1. Simulación sin gasto de créditos (`--dry-run`)
> [!TIP]
> Usa siempre `--dry-run` para revisar qué registros se procesarían sin hacer peticiones a Apify ni consumir créditos.
```bash
python enrich_graduates.py --dry-run --sheet DIQ --limit 5
```

### 2. Procesar lotes pequeños (Control de consumo)
Para procesar un número específico de egresados de una hoja determinada:
```bash
# Procesa únicamente los primeros 3 egresados de DIQ (Doctorado)
python enrich_graduates.py --sheet DIQ --limit 3

# Procesa los primeros 10 egresados de MIA (Maestría en Ing. Ambiental)
python enrich_graduates.py --sheet MIA --limit 10
```

### 3. Procesar una hoja completa o reanudar
El script cuenta con **checkpointing automático**: al ejecutarse, salta automáticamente cualquier fila que ya tenga una URL válida de LinkedIn escrita.
```bash
# Procesa o reanuda la hoja DIQ completa
python enrich_graduates.py --sheet DIQ

# Procesa o reanuda todas las hojas (DIQ, MIA, MIQ, IQ)
python enrich_graduates.py --sheet all
```

### Parámetros disponibles en `enrich_graduates.py`:
| Parámetro | Valor por defecto | Descripción |
| :--- | :--- | :--- |
| `--dry-run` | `False` | Simulación segura sin conexión a la API ni consumo de créditos. |
| `--sheet` | `all` | Hoja a procesar: `IQ`, `MIQ`, `MIA`, `DIQ`, o `all`. |
| `--limit` | `None` | Límite máximo de filas a procesar por hoja. |
| `--start-row` | `0` | Índice de fila inicial desde donde comenzar (0-indexed). |
| `--min-score` | `65` | Puntuación mínima (0-100) para aceptar un perfil como coincidencia válida. |
| `--delay` | `1.0` | Tiempo de espera en segundos entre peticiones consecutivas a Apify. |
| `--input` | Archivo original | Ruta del archivo Excel de entrada. |
| `--output` | Archivo enriquecido | Ruta del archivo Excel enriquecido de salida. |

---

## 🧪 Pruebas Unitarias (Offline)

Para verificar la lógica de scoring, normalización de acentos y separación de apellidos sin gastar créditos de Apify:

```bash
python test_enrich_graduates.py
```
*(Debe reportar `Ran 5 tests in 0.001s, OK`)*
