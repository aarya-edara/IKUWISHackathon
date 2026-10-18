import datetime
import os.path


from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def getNext10Events(creds):

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

def getAllEventsInADay(creds,Date,CalendarID):

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        StartDate = Date
        EndDate = (StartDate + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        print("Getting all events on a specified date")
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
    except:
       print("Another error occurred")

def getAllEventsInACalendar(creds,CalendarID):

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

def getAllCalendarIDs(creds):
    # Google API for getting all events in calendaer
    service = build("calendar", "v3", credentials=creds)
    AllCalendars = service.calendarList().list(maxResults=250).execute().get("items", [])

    allCalendarsIDs = []
    for calendar in AllCalendars:
        # Get calendar ID
        allCalendarsIDs.append(calendar["id"])

    return allCalendarsIDs

def getDailyEventsInAllCalendars(creds):
    AllCalendarsIDs = getAllCalendarIDs(creds)
    events = []
    Date = datetime.datetime.now(tz=datetime.timezone.utc)
    for ID in AllCalendarsIDs:
        events.extend(getAllEventsInADay(creds,Date,ID))

    return events

def getAllEventsInAllCalendars(creds):
    AllCalendarsIDs = getAllCalendarIDs(creds)
    events = []

    for ID in AllCalendarsIDs:
        events.extend(getAllEventsInACalendar(creds,ID))

    return events

def main():

    # Authenticate User Start ↓↓↓
    creds = authenticateUserCredentials()
    # Authenticate User End ↑↑↑

    # events = getNext10Events(creds)
    # events = getAllEventsInACalendar(creds,'CALENDAR ID HERE')
    # events = getAllEventsInAllCalendars(creds)
    events = getDailyEventsInAllCalendars(creds)
    # Today = datetime.datetime.now(tz=datetime.timezone.utc)
    # events = getAllEventsInADay(creds,Today)
    printAllEventsInTerminal(events)



if __name__ == "__main__":
  main()