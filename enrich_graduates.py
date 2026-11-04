import argparse
import glob
import json
import logging
import os
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from openpyxl import load_workbook

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("enrich_graduates")


def normalize_text(text: Optional[str]) -> str:
    """Normaliza texto eliminando tildes y pasando a minúsculas para comparaciones flexibles."""
    if not text or pd.isna(text):
        return ""
    text = str(text).strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def get_apify_token() -> str:
    """Recupera el token de Apify desde .env o el caché local de OAuth."""
    token = os.getenv("APIFY_TOKEN")
    if token and token.strip() and token != "your_apify_token_here":
        return token.strip()

    mcp_auth_dir = Path.home() / ".mcp-auth" / "mcp-remote-v1"
    token_files = glob.glob(str(mcp_auth_dir / "*_tokens.json"))
    for file_path in token_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                oauth_token = data.get("access_token")
                if oauth_token:
                    return oauth_token
        except Exception:
            continue

    logger.error("No se encontró token de Apify en .env ni en ~/.mcp-auth/")
    sys.exit(1)


def parse_names(row: pd.Series, sheet_name: str) -> Tuple[str, str, str]:
    """
    Extrae (firstName, lastName_completo, primer_apellido) según la estructura de la hoja.
    """
    first_name = str(row.get("Nombres", "")).strip()

    if sheet_name == "IQ":
        ap1 = str(row.get("Apellidos_1", "")).strip() if pd.notna(row.get("Apellidos_1")) else ""
        ap2 = str(row.get("Apellidos_2", "")).strip() if pd.notna(row.get("Apellidos_2")) else ""
        full_last = f"{ap1} {ap2}".strip()
        first_last = ap1 if ap1 else full_last
    else:
        full_last = str(row.get("Apellidos", "")).strip() if pd.notna(row.get("Apellidos")) else ""
        parts = full_last.split()
        first_last = parts[0] if parts else full_last

    return first_name, full_last, first_last


def score_candidate(candidate: Dict[str, Any], first_name: str, last_name: str, sheet_name: str) -> Tuple[int, List[str]]:
    """
    Calcula un puntaje de 0 a 100 para evaluar si un perfil de LinkedIn coincide con el egresado.
    """
    score = 0
    reasons = []

    c_first = normalize_text(candidate.get("firstName"))
    c_last = normalize_text(candidate.get("lastName"))
    c_headline = normalize_text(candidate.get("headline"))
    target_first = normalize_text(first_name)
    target_last = normalize_text(last_name)

    # 1. Coincidencia de nombre
    target_first_words = [w for w in target_first.split() if len(w) > 2]
    matched_first_words = sum(1 for w in target_first_words if w in c_first)
    if matched_first_words > 0:
        score += 25
        reasons.append("Nombre coincidente")

    # 2. Coincidencia de apellido
    target_last_words = [w for w in target_last.split() if len(w) > 2]
    matched_last_words = sum(1 for w in target_last_words if w in c_last)
    if matched_last_words > 0:
        score += 25
        reasons.append(f"Apellido coincidente ({matched_last_words}/{len(target_last_words)})")

    # 3. Educación en Universidad Nacional de Colombia
    educations = candidate.get("education", []) or []
    has_unal = False
    has_career = False

    for edu in educations:
        school = normalize_text(edu.get("schoolName"))
        degree = normalize_text(edu.get("degree"))
        field = normalize_text(edu.get("fieldOfStudy"))
        edu_text = f"{degree} {field}"

        if "nacional de colombia" in school or "unal" in school:
            has_unal = True

        if sheet_name in ["IQ", "MIQ", "DIQ"]:
            if "quimic" in edu_text or "chemical" in edu_text:
                has_career = True
        elif sheet_name == "MIA":
            if "ambiental" in edu_text or "environmental" in edu_text:
                has_career = True

    if has_unal:
        score += 30
        reasons.append("Educación: UNAL confirmada")

    # 4. Afinidad temática en carrera o titular
    if sheet_name in ["IQ", "MIQ", "DIQ"]:
        if has_career or "quimic" in c_headline or "chemical" in c_headline:
            score += 20
            reasons.append("Área: Química identificada")
    elif sheet_name == "MIA":
        if has_career or "ambiental" in c_headline or "environmental" in c_headline:
            score += 20
            reasons.append("Área: Ambiental identificada")

    return score, reasons


class LinkedInEnricher:
    def __init__(
        self,
        input_excel: str,
        output_excel: str,
        token: Optional[str] = None,
        dry_run: bool = False,
        school_filter: str = "Universidad Nacional de Colombia",
        min_score: int = 65,
        delay_seconds: float = 1.0,
    ):
        self.input_excel = input_excel
        self.output_excel = output_excel
        self.dry_run = dry_run
        self.school_filter = school_filter
        self.min_score = min_score
        self.delay_seconds = delay_seconds
        self.client = None

        if not dry_run:
            from apify_client import ApifyClient
            self.client = ApifyClient(token or get_apify_token())

        self._ensure_output_file()

    def _ensure_output_file(self):
        """Copia el archivo original si el destino aún no existe."""
        if not os.path.exists(self.output_excel):
            logger.info(f"Creando archivo de salida inicial: {self.output_excel}")
            shutil.copyfile(self.input_excel, self.output_excel)

    def search_person(self, first_name: str, last_name: str) -> List[Dict[str, Any]]:
        """Realiza la consulta al Actor de Apify con el filtro escolar."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Simulación de búsqueda para: {first_name} {last_name}")
            return []

        run_input = {
            "profileScraperMode": "Full",
            "firstName": first_name,
            "lastName": last_name,
            "strictSearch": False,
            "maxPages": 1,
            "schools": [self.school_filter] if self.school_filter else [],
        }

        try:
            run = self.client.actor("harvestapi/linkedin-profile-search-by-name").call(
                run_input=run_input
            )
            if not run:
                return []
            dataset_id = getattr(run, "default_dataset_id", None) or (
                run.get("defaultDatasetId") if isinstance(run, dict) else None
            )
            if not dataset_id:
                return []
            items = list(self.client.dataset(dataset_id).iterate_items())
            return items
        except Exception as e:
            logger.error(f"Error al consultar Apify para {first_name} {last_name}: {e}")
            return []

    def process_sheet(self, sheet_name: str, limit: Optional[int] = None, start_row: int = 0):
        """Procesa una hoja específica con guardado celda a celda."""
        logger.info(f"--- Procesando hoja: {sheet_name} ---")

        # Leer archivo actual de salida para checkpointing
        df = pd.read_excel(self.output_excel, sheet_name=sheet_name)
        total_rows = len(df)
        logger.info(f"Total registros en {sheet_name}: {total_rows}")

        # Identificar columna Perfil LinkedIn
        if "Perfil LinkedIn" not in df.columns:
            logger.warning(f"La hoja {sheet_name} no tiene columna 'Perfil LinkedIn'. Omitiendo.")
            return

        # Cargar workbook de openpyxl para actualizar celdas conservando formato
        wb = load_workbook(self.output_excel)
        ws = wb[sheet_name]

        # Encontrar índice de columna 'Perfil LinkedIn' en openpyxl (1-indexed)
        header_row = 1
        linkedin_col_idx = None
        for col_idx in range(1, ws.max_column + 1):
            val = ws.cell(row=header_row, column=col_idx).value
            if val and str(val).strip() == "Perfil LinkedIn":
                linkedin_col_idx = col_idx
                break

        if not linkedin_col_idx:
            logger.error(f"No se encontró la columna 'Perfil LinkedIn' en {sheet_name}")
            return

        processed_count = 0
        matches_count = 0

        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            if limit is not None and processed_count >= limit:
                logger.info(f"Límite alcanzado de {limit} filas para la hoja {sheet_name}.")
                break

            excel_row_num = idx + 2  # openpyxl es 1-indexed y la fila 1 es encabezado
            existing_value = ws.cell(row=excel_row_num, column=linkedin_col_idx).value

            # Si ya tiene un valor válido (no vacío ni 'No encontrado'), continuar
            if existing_value and pd.notna(existing_value) and str(existing_value).strip().startswith("http"):
                continue

            first_name, last_name, first_last = parse_names(row, sheet_name)
            if not first_name or pd.isna(first_name):
                continue

            processed_count += 1
            logger.info(f"[{processed_count}] ({sheet_name} Fila {idx + 1}/{total_rows}) Buscando: {first_name} {last_name}")

            if self.dry_run:
                continue

            # Buscar en Apify
            candidates = self.search_person(first_name, last_name)

            # Si no hay resultados con ambos apellidos, intentar con primer apellido
            if not candidates and first_last and first_last != last_name:
                logger.info(f"Reintentando con primer apellido: {first_name} {first_last}")
                candidates = self.search_person(first_name, first_last)

            best_profile = None
            highest_score = 0
            best_reasons = []

            for cand in candidates:
                cand_score, cand_reasons = score_candidate(cand, first_name, last_name, sheet_name)
                if cand_score > highest_score:
                    highest_score = cand_score
                    best_profile = cand
                    best_reasons = cand_reasons

            if best_profile and highest_score >= self.min_score:
                url = best_profile.get("linkedinUrl", "")
                ws.cell(row=excel_row_num, column=linkedin_col_idx, value=url)
                wb.save(self.output_excel)
                matches_count += 1
                logger.info(f"  🎯 Match encontrado ({highest_score} pts: {', '.join(best_reasons)}): {url}")
            else:
                ws.cell(row=excel_row_num, column=linkedin_col_idx, value="No encontrado")
                wb.save(self.output_excel)
                logger.info("  ⚠️ Sin coincidencia confiable. Marcado como 'No encontrado'")

            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)

        wb.close()
        logger.info(f"Hoja {sheet_name} finalizada. Procesados: {processed_count}, Matches encontrados: {matches_count}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Enriquecer archivo Excel de egresados con perfiles de LinkedIn usando Apify"
    )
    parser.add_argument(
        "--input",
        default="PAE-Organización Egresados_Version2026-2S.xlsx",
        help="Archivo Excel de entrada con egresados",
    )
    parser.add_argument(
        "--output",
        default="PAE-Organizacion_Egresados_Enriquecido.xlsx",
        help="Archivo Excel de salida enriquecido",
    )
    parser.add_argument(
        "--sheet",
        choices=["IQ", "MIQ", "MIA", "DIQ", "all"],
        default="all",
        help="Hoja a procesar (IQ, MIQ, MIA, DIQ, o all para todas)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de personas a procesar por hoja",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=0,
        help="Índice de fila inicial desde donde comenzar (0-indexed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo simulación: no realiza llamadas a Apify ni gasta créditos",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=65,
        help="Puntaje mínimo de coincidencia para aceptar un perfil (0 a 100)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Segundos de espera entre cada consulta",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    enricher = LinkedInEnricher(
        input_excel=args.input,
        output_excel=args.output,
        dry_run=args.dry_run,
        min_score=args.min_score,
        delay_seconds=args.delay,
    )

    sheets_to_process = (
        ["DIQ", "MIA", "MIQ", "IQ"] if args.sheet == "all" else [args.sheet]
    )

    for sheet in sheets_to_process:
        enricher.process_sheet(
            sheet_name=sheet,
            limit=args.limit,
            start_row=args.start_row,
        )
