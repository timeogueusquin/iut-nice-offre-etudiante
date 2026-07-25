"""Orchestration de la collecte des sources legales."""

import json
import os
import time
from datetime import datetime
import base64
import gspread
from google.oauth2.service_account import Credentials

from src.config import CONFIGS as DEFAULT_CONFIGS
from src.utils import save_sheet_excel
from src.scrapers.legal_sources.common import fetch_source_safely, source_enabled
from src.scrapers.legal_sources.settings import (
    DOMAINES_A_LANCER as DEFAULT_DOMAINES_A_LANCER,
    DOMAIN_ROMES as DEFAULT_DOMAIN_ROMES,
    TITLE_DOMAIN_KEYWORDS as DEFAULT_TITLE_DOMAIN_KEYWORDS,
    LBA_JOB_NAMES as DEFAULT_LBA_JOB_NAMES,
    MANUAL_API_SOURCES,
    RSS_SOURCES,
    SOURCE_NAMES,
)
from src.scrapers.legal_sources.sources.cea import fetch_rss_source
from src.scrapers.legal_sources.sources.france_travail import fetch_france_travail
from src.scrapers.legal_sources.sources.la_bonne_alternance import fetch_la_bonne_alternance
from src.scrapers.legal_sources.sources.pass_fonction_publique import fetch_pass_fonction_publique
from src.counters import start, stop

CONFIG_SHEET_NAME = "CONFIG_FORMATIONS"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

def split_values(value):
    """Transforme une cellule Google Sheets separee par virgules en liste propre."""
    if value is None:
        return []

    return [
        item.strip()
        for item in str(value).split(",")
        if item.strip()
    ]

def is_active_value(value):
    """Interprete les valeurs utilisateur qui activent une formation."""
    value = str(value or "").strip().lower()

    return value in {
        "oui",
        "yes",
        "true",
        "1",
        "actif",
        "active",
        "on",
    }

def get_google_service_account_info():
    """Charge les identifiants Google depuis les formats acceptes en local ou CI."""
    raw_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "").strip()

    if raw_b64:
        decoded = base64.b64decode(raw_b64).decode("utf-8")
        return json.loads(decoded)

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if raw_json:
        return json.loads(raw_json)

    required_keys = [
        "GOOGLE_TYPE",
        "GOOGLE_PROJECT_ID",
        "GOOGLE_PRIVATE_KEY_ID",
        "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_AUTH_URI",
        "GOOGLE_TOKEN_URI",
        "GOOGLE_AUTH_PROVIDER_CERT_URL",
        "GOOGLE_CLIENT_CERT_URL",
    ]

    if all(os.environ.get(key) for key in required_keys):
        return {
            "type": os.environ["GOOGLE_TYPE"],
            "project_id": os.environ["GOOGLE_PROJECT_ID"],
            "private_key_id": os.environ["GOOGLE_PRIVATE_KEY_ID"],
            "private_key": os.environ["GOOGLE_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["GOOGLE_CLIENT_EMAIL"],
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "auth_uri": os.environ["GOOGLE_AUTH_URI"],
            "token_uri": os.environ["GOOGLE_TOKEN_URI"],
            "auth_provider_x509_cert_url": os.environ["GOOGLE_AUTH_PROVIDER_CERT_URL"],
            "client_x509_cert_url": os.environ["GOOGLE_CLIENT_CERT_URL"],
        }

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

    if credentials_path:
        with open(credentials_path, "r", encoding="utf-8") as file:
            return json.load(file)

    return None

def load_config_rows_from_google_sheet():
    """Lit la feuille de configuration des formations depuis Google Sheets."""
    sheet_id = (
        os.environ.get("GOOGLE_CONFIG_SHEET_ID", "").strip()
        or os.environ.get("GOOGLE_SHEET_ID", "").strip()
    )

    if not sheet_id:
        raise RuntimeError(
            "GOOGLE_CONFIG_SHEET_ID ou GOOGLE_SHEET_ID manquant."
        )

    service_account_info = get_google_service_account_info()

    if not service_account_info:
        raise RuntimeError(
            "Identifiants Google manquants. Configure GOOGLE_SERVICE_ACCOUNT_JSON "
            "ou GOOGLE_APPLICATION_CREDENTIALS."
        )

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=GOOGLE_SCOPES,
    )

    client = gspread.authorize(creds)
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            spreadsheet = client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(CONFIG_SHEET_NAME)
            return worksheet.get_all_records()
        except Exception as exc:
            if attempt == max_retries:
                raise
            delay = attempt * 3
            time.sleep(delay)

def get_row_value_with_fallbacks(row, keys):
    """Récupère la valeur d'une ligne Google Sheet avec gestion robuste de clés alternatives (ex: avec ou sans accents)."""
    for key in keys:
        if key in row and row[key] is not None and str(row[key]).strip() != "":
            return str(row[key]).strip()
    for key in keys:
        if key in row:
            return str(row[key] or "").strip()
    return ""

def build_runtime_config_from_rows(rows):
    """Construit les configs de collecte a partir des lignes Google Sheets."""
    configs = {}
    domaines_a_lancer = []
    domain_romes = {}
    title_domain_keywords = {}
    lba_job_names = {}

    for row in rows:
        code = get_row_value_with_fallbacks(row, ["Code"]).strip().upper()
        nom = get_row_value_with_fallbacks(row, ["Nom"]).strip()
        active = get_row_value_with_fallbacks(row, ["Activé", "Active", "Actif"])

        if not code:
            continue

        if not is_active_value(active):
            continue

        # Les champs texte de la feuille alimentent les mots-cles, titres, ROME et exclusions.
        keywords = split_values(get_row_value_with_fallbacks(row, ["Mots clés description", "Mots cles description", "Mots clés", "Mots cles"]))
        title_keywords = split_values(get_row_value_with_fallbacks(row, ["Mots clés titre", "Mots cles titre"]))
        romes = split_values(get_row_value_with_fallbacks(row, ["Codes ROME", "Codes Rome"]))
        exclude_keywords = split_values(get_row_value_with_fallbacks(row, ["Mots exclus titre", "Mots cles exclus titre", "Mots exclus", "Mots cles exclus"]))

        # Lecture du nombre de compétences techniques exigées (défaut = 2)
        min_comps_val = get_row_value_with_fallbacks(row, ["Compétences exigées", "Competences exigees", "Nombre compétences", "Nombre competences"])
        min_competences = 2
        if min_comps_val:
            try:
                min_competences = int(float(min_comps_val))
            except ValueError:
                pass

        # Lecture du nombre de mots-clés titre exigés (défaut = 0)
        min_title_val = get_row_value_with_fallbacks(row, ["Mots clés titre exigés", "Mots cles titre exigés", "Nombre mots cles titre"])
        min_mots_cles_titre = 0
        if min_title_val:
            try:
                min_mots_cles_titre = int(float(min_title_val))
            except ValueError:
                pass

        # Lecture du nombre de mots-clés description exigés (défaut = 0)
        min_desc_val = get_row_value_with_fallbacks(row, ["Mots clés description exigés", "Mots cles description exigés", "Nombre mots cles description"])
        min_mots_cles_desc = 0
        if min_desc_val:
            try:
                min_mots_cles_desc = int(float(min_desc_val))
            except ValueError:
                pass

        # On ne conserve du code local que la configuration des études (non présente dans Google Sheet).
        # Les compétences, mots-clés et exclusions proviennent exclusivement du Google Sheet pour éviter tout conflit.
        base_config = {
            "nom_export": DEFAULT_CONFIGS.get(code, {}).get("nom_export", code.lower()),
            "etudes": DEFAULT_CONFIGS.get(code, {}).get("etudes", {}),
            "competences": {},
            "keywords": [],
            "exclude_keywords": []
        }
        base_config["min_competences"] = min_competences
        base_config["min_mots_cles_titre"] = min_mots_cles_titre
        base_config["min_mots_cles_desc"] = min_mots_cles_desc

        # Parsing des compétences personnalisées depuis Google Sheet si fournies
        competences_str = get_row_value_with_fallbacks(row, ["Compétences", "Competences"])
        if competences_str:
            parsed_competences = {}
            import re
            # Regex qui découpe les catégories y compris en cas de remplacement erroné des points-virgules par des virgules
            parts = re.split(r'([^,;:]+):', competences_str)
            if len(parts) > 1:
                for i in range(1, len(parts) - 1, 2):
                    comp_name = parts[i].strip()
                    keywords_raw = parts[i+1].strip()
                    # Nettoie les résidus de virgules/points-virgules de début/fin
                    keywords_raw = re.sub(r'^[,;\s]+|[,;\s]+$', '', keywords_raw)
                    kws = [
                        k.strip()
                        for k in keywords_raw.replace("/", ",").split(",")
                        if k.strip()
                    ]
                    if comp_name and kws:
                        parsed_competences[comp_name] = kws
            else:
                # Fallback simple par split
                parts = competences_str.split(";")
                for part in parts:
                    if not part.strip():
                        continue
                    if ":" in part:
                        comp_name, keywords_raw = part.split(":", 1)
                        comp_name = comp_name.strip()
                        kws = [
                            k.strip()
                            for k in keywords_raw.replace("/", ",").split(",")
                            if k.strip()
                        ]
                        if comp_name and kws:
                            parsed_competences[comp_name] = kws
            if parsed_competences:
                base_config["competences"] = parsed_competences


        if nom:
            base_config["name"] = nom

        if keywords:
            base_config["keywords"] = keywords

        if exclude_keywords:
            base_config["exclude_keywords"] = exclude_keywords
        else:
            base_config["exclude_keywords"] = base_config.get("exclude_keywords", [])

        configs[code] = base_config
        domaines_a_lancer.append(code)
        domain_romes[code] = romes
        title_domain_keywords[code] = title_keywords
        lba_job_names[code] = ", ".join(keywords)

    return configs, domaines_a_lancer, domain_romes, title_domain_keywords, lba_job_names

def patch_sources_runtime_settings(domain_romes, title_domain_keywords, lba_job_names):
    """Synchronise les constantes importees par les modules de sources."""
    import src.scrapers.legal_sources.settings as settings

    settings.DOMAIN_ROMES = domain_romes
    settings.TITLE_DOMAIN_KEYWORDS = title_domain_keywords
    settings.LBA_JOB_NAMES = lba_job_names

    try:
        import src.scrapers.legal_sources.sources.la_bonne_alternance as lba_source

        lba_source.DOMAIN_ROMES = domain_romes
        lba_source.LBA_JOB_NAMES = lba_job_names
        lba_source.TITLE_DOMAIN_KEYWORDS = title_domain_keywords
    except Exception:
        pass

    try:
        import src.scrapers.legal_sources.sources.cea as rss_source

        rss_source.TITLE_DOMAIN_KEYWORDS = title_domain_keywords
    except Exception:
        pass

def load_runtime_config():
    """Charge la configuration dynamique, avec fallback sur les valeurs du code."""
    use_google_config = os.environ.get(
        "USE_GOOGLE_FORMATION_CONFIG",
        "1",
    ).strip().lower()

    if use_google_config in {"0", "false", "no", "non", "off"}:
        return (
            DEFAULT_CONFIGS,
            DEFAULT_DOMAINES_A_LANCER,
            DEFAULT_DOMAIN_ROMES,
            DEFAULT_TITLE_DOMAIN_KEYWORDS,
            DEFAULT_LBA_JOB_NAMES,
        )

    try:
        rows = load_config_rows_from_google_sheet()
        runtime = build_runtime_config_from_rows(rows)

        configs, domaines_a_lancer, domain_romes, title_domain_keywords, lba_job_names = runtime

        if not domaines_a_lancer:
            raise RuntimeError(
                f"Aucune formation active trouvée dans {CONFIG_SHEET_NAME}."
            )

        patch_sources_runtime_settings(
            domain_romes,
            title_domain_keywords,
            lba_job_names,
        )

        print(
            f"Configuration formations chargée depuis Google Sheets : "
            f"{len(domaines_a_lancer)} formations actives."
        )
        for code, cfg in configs.items():
            print(f"  - BUT {code} : compétences_exigées={cfg.get('min_competences')}, mots_clés_titre_exigés={cfg.get('min_mots_cles_titre')}, mots_clés_description_exigés={cfg.get('min_mots_cles_desc')}")

        return runtime

    except Exception as exc:
        print(
            "Configuration Google Sheets indisponible. "
            f"Fallback sur la configuration du code : {exc}"
        )

        return (
            DEFAULT_CONFIGS,
            DEFAULT_DOMAINES_A_LANCER,
            DEFAULT_DOMAIN_ROMES,
            DEFAULT_TITLE_DOMAIN_KEYWORDS,
            DEFAULT_LBA_JOB_NAMES,
        )

def fetch_manual_api_sources():
    """Affiche les sources connues mais non activees faute d'endpoint officiel."""
    for source, settings in MANUAL_API_SOURCES.items():
        if source_enabled(source):
            print(f"{source} non collecté : {settings['reason']} ({settings['url']})")

def fetch_all_for_config(config_name, config):
    """Lance toutes les sources activees pour un departement IUT."""
    jobs_by_source = {source: [] for source in SOURCE_NAMES}

    print("\n==============================")
    print(f"Collecte sources légales : {config_name}")
    print("==============================")

    collectors = {
        "France Travail API": lambda: fetch_france_travail(config_name, config),
        "La Bonne Alternance": lambda: fetch_la_bonne_alternance(config_name, config),
        "PASS Fonction publique": lambda: fetch_pass_fonction_publique(config_name, config),
    }

    # Les collecteurs principaux ont chacun leur module et leur gestion d'erreurs.
    for source, fetcher in collectors.items():
        if not source_enabled(source):
            continue

        start()
        jobs_by_source[source] = fetch_source_safely(source, fetcher)
        stop(source)
        print(f"{source} : {len(jobs_by_source[source])} offres")
        time.sleep(0.5)

    for source, urls in RSS_SOURCES.items():
        if not source_enabled(source):
            continue

        start()
        jobs_by_source[source] = fetch_source_safely(
            source,
            lambda source=source, urls=urls: fetch_rss_source(
                source,
                urls,
                config,
                config_name,
            ),
        )
        stop(source)
        print(f"{source} : {len(jobs_by_source[source])} offres")
        time.sleep(0.5)

    fetch_manual_api_sources()

    return jobs_by_source

def should_save_source_sheet(source):
    """En mode CI parallele, evite de reecrire les feuilles des sources non lancees."""
    save_only_enabled = os.environ.get(
        "LEGAL_JOB_SAVE_ONLY_ENABLED",
        "",
    ).strip().lower()

    if save_only_enabled in {"1", "true", "yes", "oui"}:
        return source_enabled(source)

    return True

def main():
    """Point d'entree appele par GitHub Actions et par le script historique."""
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("Début collecte légale :", started_at)

    configs, domaines_a_lancer, _, _, _ = load_runtime_config()

    for domaine in domaines_a_lancer:
        config = configs.get(domaine)

        if not config:
            print(f"Domaine ignoré : configuration introuvable pour {domaine}.")
            continue

        jobs_by_source = fetch_all_for_config(domaine, config)

        for source in SOURCE_NAMES:
            if not should_save_source_sheet(source):
                continue

            jobs = jobs_by_source.get(source, [])
            save_sheet_excel(jobs, config, sheet_name=source[:31])

    print("Collecte légale terminée.")

if __name__ == "__main__":
    main()
