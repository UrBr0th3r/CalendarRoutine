import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Permessi richiesti: lettura e scrittura sul calendario
SCOPES = ['https://www.googleapis.com/auth/calendar']


def get_calendar_service():
    creds = None
    # Il file token.json memorizza i token di accesso e di refresh dell'utente
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # Se non ci sono credenziali valide disponibili, fai accedere l'utente
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Salva le credenziali per le successive esecuzioni
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendarAPI', 'v3', credentials=creds)