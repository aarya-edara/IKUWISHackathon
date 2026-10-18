import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def authenticateUserCredentials():
    try:
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=8080)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        return creds
    except:
        print("Credentials are invalid or not set up")
        print("https://developers.google.com/workspace/calendar/api/quickstart/python")


def getNext10Events():

    # Authenticate User Start ↓↓↓
    creds  = authenticateUserCredentials()
    # Authenticate User End ↑↑↑

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        print("Getting the upcoming 10 events")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return events


    except HttpError as error:
        print(f"An error occurred: {error}")
    except:
        print("Another error occurred")

def getAllEventsInADay(Date):
    # Authenticate User Start ↓↓↓
    creds = authenticateUserCredentials()
    # Authenticate User End ↑↑↑

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        StartDate = Date
        EndDate = (StartDate + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        print("Getting all events on a specified date")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=StartDate.isoformat(),
                timeMax =EndDate.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return events

    except HttpError as error:
        print(f"An error occurred: {error}")
    except:
       print("Another error occurred")

def getAllEventsInCalendar(CalendarID):
    # Authenticate User Start ↓↓↓
    creds = authenticateUserCredentials()
    # Authenticate User End ↑↑↑

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        ## NOTE : HARDCODED DATES
        StartDate = datetime.datetime.now(tz=datetime.timezone.utc)
        EndDate = (StartDate + datetime.timedelta(days=180)).replace(hour=0, minute=0, second=0, microsecond=0)
        print("Getting all events within a 6 month period [6 months for demo purposes]")
        events_result = (
            service.events()
            .list(
                calendarId=CalendarID,
                timeMin=StartDate.isoformat(),
                timeMax =EndDate.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return events

    except HttpError as error:
        print(f"An error occurred: {error}")
    # except:
    #     print("Another error occurred")




def printAllEventsInTerminal(Events):
    try :
        for event in Events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            print(start, event["summary"])
    except TypeError:
        print("No upcoming events found.")


def main():
    # events = getNext10Events()
    events = getAllEventsInCalendar('vjnbcrcpdoc16ao7bghfaun2j1sv11b9@import.calendar.google.com')
    # Today = datetime.datetime.now(tz=datetime.timezone.utc)
    # events = getAllEventsInADay(Today)
    printAllEventsInTerminal(events)


if __name__ == "__main__":
  main()