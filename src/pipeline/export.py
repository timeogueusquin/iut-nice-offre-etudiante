# export.py

import logging
import os
import base64
import pandas as pd
import gspread

from google.oauth2.service_account import Credentials
from src.utils import COLUMNS

logger = logging.getLogger(__name__)

# CONFIG

SERVICE_ACCOUNT_FILE = "credentials.json"

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "1DNQZRR55YODMen7NSfEKrmGR9ygSd9yIda0S5-X-TVU")

EXCEL_FILE = "exports/offres_fusion_par_departement.xlsx"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEETS = [
    "CS",
    "GEA",
    "GEII",
    "INFO",
    "INFOCOM",
    "QLIO",
    "RT",
    "SD",
    "TC",
]

STUDENT_CONTRACTS = ["stage", "alternance"]

# CREDENTIALS

def ensure_credentials_file():
    """
    Local :
    - utilise credentials.json s'il existe.

    GitHub Actions :
    - recrée credentials.json depuis le secret GOOGLE_CREDENTIALS_B64.
    """
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        return

    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")

    if not creds_b64:
        raise FileNotFoundError(
            "credentials.json introuvable et secret GOOGLE_CREDENTIALS_B64 absent."
        )

    creds_json = base64.b64decode(creds_b64).decode("utf-8")

    with open(SERVICE_ACCOUNT_FILE, "w", encoding="utf-8") as f:
        f.write(creds_json)

    logger.info("credentials.json recréé depuis GOOGLE_CREDENTIALS_B64")

# GOOGLE SHEETS

def retry_api_call(func, max_retries=5, initial_delay=3):
    """Exécute une fonction d'appel API Google avec réessais en cas d'erreur 503 ou réseau temporaire."""
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            delay = initial_delay * attempt
            logger.warning("Tentative API Google %d/%d échouée (%s). Retentative dans %ds...", attempt, max_retries, e, delay)
            time.sleep(delay)

def connect_google_sheet():
    """Ouvre le classeur Google Sheets cible avec le compte de service."""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    client = gspread.authorize(creds)

    return retry_api_call(lambda: client.open_by_key(GOOGLE_SHEET_ID))

def get_or_create_worksheet(spreadsheet, sheet_name, rows=1000):
    """Recupere une feuille existante ou la cree avec les colonnes attendues."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)

    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=rows,
            cols=len(COLUMNS)
        )

    try:
        worksheet.resize(
            rows=rows,
            cols=len(COLUMNS)
        )
    except Exception:
        pass

    return worksheet

# DATAFRAME

def prepare_dataframe(df):
    """Nettoie les donnees avant publication dans Google Sheets."""
    df = df.fillna("")

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[COLUMNS]

    weekly_time = (
        df["Temps"]
        .astype(str)
        .str.lower()
        .str.contains(r"temps plein|temps partiel|\b\d{1,2}\s*h", regex=True)
    )

    # La colonne Temps doit contenir une duree de contrat, pas un horaire hebdomadaire.
    df.loc[weekly_time, "Temps"] = "Non précisé"

    # Les lignes sans lien ne sont pas exploitables dans l'interface.
    df = df[
        df["Lien"].astype(str).str.strip() != ""
    ]

    contract = df["Contrat"].astype(str).str.lower().str.strip()

    df = df[contract.isin(STUDENT_CONTRACTS)]

    # Le lien source est l'identifiant le plus fiable pour dedoublonner.
    df.drop_duplicates(
        subset=["Lien"],
        inplace=True
    )

    df["Date_tri"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    df = df.sort_values(
        by=["Date_tri"],
        ascending=[False]
    )

    df.drop(
        columns=["Date_tri"],
        inplace=True
    )

    df = df.fillna("")

    return df

def read_excel_sheet(sheet_name):
    """Lit une feuille du fichier fusionne puis applique le nettoyage commun."""
    df = pd.read_excel(
        EXCEL_FILE,
        sheet_name=sheet_name
    )

    return prepare_dataframe(df)

# UPLOAD

def upload_sheet(spreadsheet, sheet_name, df):
    """Remplace le contenu d'une feuille Google par les offres nettoyees."""
    worksheet = retry_api_call(lambda: get_or_create_worksheet(
        spreadsheet,
        sheet_name,
        rows=max(len(df) + 10, 1000)
    ))

    retry_api_call(lambda: worksheet.clear())

    values = [COLUMNS] + df[COLUMNS].astype(str).values.tolist()

    retry_api_call(lambda: worksheet.update(values))

    try:
        worksheet.freeze(rows=1)
    except Exception:
        pass

    logger.info("Feuille Google mise à jour : %s (%d offres)", sheet_name, len(df))

# MAIN

def main():
    """Exporte le classeur fusionne vers Google Sheets, feuille par feuille."""
    ensure_credentials_file()

    if not os.path.exists(EXCEL_FILE):
        print(f"Fichier introuvable : {EXCEL_FILE}")
        print("Lance d'abord : python fusion_departements.py")
        return

    logger.info("Connexion à Google Sheets...")

    spreadsheet = connect_google_sheet()

    logger.info("Connexion réussie : %s", spreadsheet.title)

    for sheet_name in SHEETS:
        logger.info("Export feuille : %s", sheet_name)

        try:
            df = read_excel_sheet(sheet_name)

        except Exception as e:
            logger.warning("Erreur lecture feuille %s : %s", sheet_name, e)
            continue

        upload_sheet(
            spreadsheet,
            sheet_name,
            df
        )

    logger.info("Export Google Sheets terminé.")

if __name__ == "__main__":
    main()
