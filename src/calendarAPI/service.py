# src/calendarAPI/service.py
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from utilities.core import Paths

class CalendarManager:
    
    credentials_path: Path
    token_path: Path

    service: Resource

    def __init__(self, credentials_path: str | Path = Paths.OAUTH / "credentials.json", token_path: str | Path = Paths.OAUTH / "token.json", *, port: int = 2212):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        scopes = ['https://www.googleapis.com/auth/calendar']
        
        if not self.credentials_path.exists():
            raise FileNotFoundError(f"File credenziali non trovato in: {self.credentials_path.resolve()}")

        creds = None
        # Il file token.json memorizza i token di accesso e di refresh dell'utente
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(str(self.token_path), scopes)

        # Se non ci sono credenziali valide disponibili, fai accedere l'utente
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path.absolute()), scopes)
                creds = flow.run_local_server(port=port)
            # Salva le credenziali per le successive esecuzioni
            if not os.path.exists(self.token_path.parent):
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())

        self.service = build('calendar', 'v3', credentials=creds)

    # def authenticate(self) -> Resource:
    # 
    #     if not self.credentials_path.exists():
    #         raise FileNotFoundError(f"File credenziali non trovato in: {self.credentials_path.resolve()}")
    # 
    #     creds = None
    #     # Il file token.json memorizza i token di accesso e di refresh dell'utente
    #     if os.path.exists(self.token_path):
    #         creds = Credentials.from_authorized_user_file(str(self.token_path), scopes)
    # 
    #     # Se non ci sono credenziali valide disponibili, fai accedere l'utente
    #     if not creds or not creds.valid:
    #         if creds and creds.expired and creds.refresh_token:
    #             creds.refresh(Request())
    #         else:
    #             flow = InstalledAppFlow.from_client_secrets_file(
    #                 str(self.credentials_path.absolute()), scopes)
    #             creds = flow.run_local_server(port=0)
    #         # Salva le credenziali per le successive esecuzioni
    #         if not os.path.exists(self.token_path.parent):
    #             self.token_path.parent.mkdir(parents=True, exist_ok=True)
    #         with open(self.token_path, 'w') as token:
    #             token.write(creds.to_json())
    # 
    #     return build('calendarAPI', 'v3', credentials=creds)

